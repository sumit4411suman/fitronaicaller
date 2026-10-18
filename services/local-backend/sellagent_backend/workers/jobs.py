"""Call Queue Worker, Campaign Engine, Follow-up Scheduler and Report Worker."""

from __future__ import annotations

import csv
import html
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sellagent_backend.db.models import Call, CallJob, Campaign, CampaignContact, Contact, Followup
from sellagent_backend.services import call_jobs, eligibility, followups, reports, settings_service
from sellagent_backend.workers.base import PeriodicWorker

# Reasons that clear by themselves; a contact blocked only by these is retried later, not excluded.
_TRANSIENT = ("quiet hours", "limit reached", "spacing", "emergency stop", "campaign has not started")


def _transient_only(reasons: list[str]) -> bool:
    return bool(reasons) and all(any(t in r for t in _TRANSIENT) for r in reasons)


class CallQueueWorker(PeriodicWorker):
    """Moves due pending jobs to `queued` after re-checking eligibility; fails dispatches nobody confirmed."""

    name = "call_queue"
    interval_s = 10.0

    def run_once_sync(self, s: Session) -> dict[str, Any]:
        queued, blocked = [], []
        for job in call_jobs.due_jobs(s):
            if job.status != "pending":
                continue
            job = call_jobs.queue(s, job.id, actor="call_queue_worker")
            (queued if job.status == "queued" else blocked).append(job.id)
        expired = call_jobs.expire_stale(s)
        waiting = s.scalar(select(func.count()).select_from(CallJob).where(CallJob.status == "queued")) or 0
        events = []
        if queued:
            events.append(("queue.ready", {"queued": queued, "waiting": int(waiting)}))
        if blocked:
            events.append(("queue.blocked", {"blocked": blocked}))
        return {"items": len(queued), "queued": len(queued), "blocked": len(blocked), "expired": expired, "waiting": int(waiting), "_events": events}


class CampaignEngineWorker(PeriodicWorker):
    """For each ACTIVE campaign, creates at most one eligible call job per tick, keeping a short operator queue
    and respecting consent, suppression, quiet hours, rate limits and the campaign's daily cap."""

    name = "campaign_engine"
    interval_s = 60.0

    def run_once_sync(self, s: Session) -> dict[str, Any]:
        if not settings_service.get(s, "workers.campaign_engine_enabled") or settings_service.get(s, "calling.emergency_stop_active"):
            return {"items": 0, "skipped": "disabled or emergency stop"}
        max_open = int(settings_service.get(s, "workers.max_open_jobs_per_campaign"))
        created: list[str] = []
        excluded = 0
        completed: list[str] = []
        for camp in s.scalars(select(Campaign).where(Campaign.status == "active")):
            open_jobs = s.scalar(select(func.count()).select_from(CallJob).where(CallJob.campaign_id == camp.id, CallJob.status.in_(("pending", "queued", "dispatched", "in_progress")))) or 0
            if open_jobs >= max_open:
                continue
            members = list(s.scalars(select(CampaignContact).where(CampaignContact.campaign_id == camp.id, CampaignContact.status.in_(("pending", "called"))).order_by(CampaignContact.created_at)))
            if not members:
                if not s.scalar(select(func.count()).select_from(CallJob).where(CallJob.campaign_id == camp.id, CallJob.status.in_(("pending", "queued", "dispatched", "in_progress")))):
                    camp.status = "completed"
                    completed.append(camp.id)
                continue
            for m in members:
                contact = s.get(Contact, m.contact_id)
                if contact is None:
                    continue
                if m.status == "called" and m.attempts >= camp.max_attempts_per_contact:
                    m.status = "done"
                    continue
                if s.scalar(select(CallJob.id).where(CallJob.contact_id == contact.id, CallJob.status.in_(("pending", "queued", "dispatched", "in_progress")))):
                    continue
                if m.status == "called":
                    continue  # retries are driven by follow-ups, not by immediate re-dial
                res = eligibility.check(s, contact, campaign=camp, mode=camp.calling_mode, route="manual")
                if res.eligible:
                    job = call_jobs.create(s, contact.id, campaign_id=camp.id, mode=camp.calling_mode, route="manual", idempotency_key=f"campaign:{camp.id}:{contact.id}:{m.attempts + 1}", actor="campaign_engine")
                    created.append(job.id)
                elif _transient_only(res.reasons):
                    pass
                else:
                    m.status, m.eligibility_snapshot = "excluded", res.to_dict()
                    excluded += 1
                break  # one decision per campaign per tick (honours min spacing)
        events = [("campaign.jobs_created", {"jobs": created})] if created else []
        events += [("campaign.completed", {"campaign_id": c}) for c in completed]
        return {"items": len(created), "created": len(created), "excluded": excluded, "completed": completed, "_events": events}


class FollowupWorker(PeriodicWorker):
    """Reminds the operator before follow-ups are due, turns due call/demo follow-ups into scheduled call jobs,
    and creates automatic follow-ups after no-answer / busy / callback outcomes."""

    name = "followup_scheduler"
    interval_s = 60.0

    def run_once_sync(self, s: Session) -> dict[str, Any]:
        now = datetime.now(UTC)
        remind = timedelta(minutes=int(settings_service.get(s, "followups.remind_minutes_before")))
        reminded, jobs, auto = [], [], []
        for f in s.scalars(select(Followup).where(Followup.status == "open", Followup.notified_at.is_(None), Followup.due_at <= now + remind)):
            contact = s.get(Contact, f.contact_id)
            f.notified_at = now
            reminded.append({"followup_id": f.id, "contact_id": f.contact_id, "business_name": contact.business_name if contact else None, "due_at": f.due_at.isoformat(), "kind": f.kind})
            if f.kind in ("call", "demo") and contact and not contact.opted_out and not contact.archived:
                try:
                    job = call_jobs.create(s, contact.id, campaign_id=contact.campaign_id, route="manual", scheduled_for=f.due_at, idempotency_key=f"followup:{f.id}", actor="followup_scheduler")
                    f.call_job_id = job.id
                    jobs.append(job.id)
                except call_jobs.CallJobError:
                    pass  # an open job already exists for this contact
        if settings_service.get(s, "followups.auto_create"):
            default_days = int(settings_service.get(s, "followups.default_after_days"))
            since = now - timedelta(days=7)
            for call in s.scalars(select(Call).where(Call.outcome.in_(("no_answer", "busy", "callback_requested")), Call.ended_at >= since)):
                contact = s.get(Contact, call.contact_id)
                if contact is None or contact.opted_out or contact.archived:
                    continue
                if s.scalar(select(Followup.id).where(Followup.contact_id == contact.id, Followup.status == "open")):
                    continue
                if s.scalar(select(Followup.id).where(Followup.call_id == call.id)):
                    continue
                job = s.get(CallJob, call.call_job_id)
                camp = s.get(Campaign, job.campaign_id) if job and job.campaign_id else None
                if camp is not None and not camp.auto_followup:
                    continue
                days = camp.followup_after_days if camp else default_days
                due = (call.ended_at or now) + timedelta(days=days)
                fu = followups.create(s, contact.id, due_at=due, kind="call", note=f"Automatic follow-up after '{call.outcome}'", call_id=call.id, actor="followup_scheduler")
                auto.append(fu.id)
        events = [("followup.due", r) for r in reminded]
        if auto:
            events.append(("followup.created", {"followups": auto}))
        return {"items": len(reminded) + len(auto), "reminded": len(reminded), "jobs_created": len(jobs), "auto_created": len(auto), "_events": events}


class ReportWorker(PeriodicWorker):
    """Generates the daily report (JSON, CSV, HTML) into <data dir>/reports/<date>/ after the configured time."""

    name = "report"
    interval_s = 300.0

    def __init__(self, *a: Any, reports_dir: Path, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.reports_dir = reports_dir

    def run_once_sync(self, s: Session) -> dict[str, Any]:
        if not settings_service.get(s, "reports.daily_enabled"):
            return {"items": 0, "skipped": "disabled"}
        tz = ZoneInfo(settings_service.get(s, "general.timezone") or "Asia/Kolkata")
        local = datetime.now(UTC).astimezone(tz)
        hh, mm = (int(x) for x in str(settings_service.get(s, "reports.daily_at")).split(":"))
        if (local.hour, local.minute) < (hh, mm):
            return {"items": 0, "skipped": "before scheduled time"}
        day = local.date().isoformat()
        if (self.reports_dir / day / "summary.json").exists():
            return {"items": 0, "skipped": "already generated"}
        info = generate_report(s, self.reports_dir, day, tz)
        return {"items": 1, "report": info, "_events": [("report.ready", info)]}


def generate_report(s: Session, reports_dir: Path, day: str, tz: ZoneInfo) -> dict[str, Any]:
    start_local = datetime.fromisoformat(day).replace(tzinfo=tz)
    start, end = start_local.astimezone(UTC), (start_local + timedelta(days=1)).astimezone(UTC)
    dash = reports.dashboard(s)
    calls = s.execute(select(Call, Contact.business_name, Contact.phone_e164).join(Contact, Contact.id == Call.contact_id).where(Call.started_at >= start, Call.started_at < end).order_by(Call.started_at)).all()
    out = reports_dir / day
    out.mkdir(parents=True, exist_ok=True)
    by_outcome: dict[str, int] = {}
    rows = []
    for call, name, phone in calls:
        by_outcome[call.outcome or "open"] = by_outcome.get(call.outcome or "open", 0) + 1
        rows.append([call.started_at.astimezone(tz).strftime("%H:%M"), name, phone, call.outcome or "", call.duration_seconds or "", call.sentiment or "", call.language])
    summary = {"date": day, "generated_at": datetime.now(UTC).isoformat(), "calls": len(rows), "by_outcome": by_outcome, "contacts_total": dash["contacts_total"], "contacts_by_stage": dash["contacts_by_stage"], "followups_overdue": dash["followups_overdue"], "data_source": "live_database"}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["time", "business_name", "phone", "outcome", "duration_s", "sentiment", "language"])
    for r in rows:
        w.writerow([("'" + str(v)) if str(v)[:1] in "=+-@" else v for v in r])
    (out / "calls.csv").write_text("﻿" + buf.getvalue(), encoding="utf-8")
    trs = "".join("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in r) + "</tr>" for r in rows) or "<tr><td colspan=7>No calls on this day.</td></tr>"
    outc = "".join(f"<li>{html.escape(k)}: <b>{v}</b></li>" for k, v in sorted(by_outcome.items())) or "<li>none</li>"
    (out / "report.html").write_text(f"""<!doctype html><meta charset="utf-8"><title>SELL AGENT daily report {day}</title>
<style>body{{font-family:Segoe UI,Nirmala UI,sans-serif;background:#F7F6F2;color:#1A1A1A;margin:24px}}h1{{color:#0B0B0B}}h1 span{{color:#B8962E}}
table{{border-collapse:collapse;background:#fff;width:100%}}td,th{{border:1px solid #E6E2D6;padding:6px 8px;text-align:left}}th{{background:#0B0B0B;color:#D4AF37}}</style>
<h1>SELL <span>AGENT</span> - daily report {day}</h1><p>Calls: <b>{len(rows)}</b> &middot; Contacts: <b>{dash['contacts_total']}</b> &middot; Overdue follow-ups: <b>{dash['followups_overdue']}</b></p>
<h3>Outcomes</h3><ul>{outc}</ul><h3>Calls</h3><table><tr><th>Time</th><th>Business</th><th>Phone</th><th>Outcome</th><th>Duration (s)</th><th>Sentiment</th><th>Lang</th></tr>{trs}</table>
<p style="color:#6B665A">Generated locally from the SELL AGENT database. No data left this computer.</p>""", encoding="utf-8")
    return {"date": day, "files": ["summary.json", "calls.csv", "report.html"], "calls": len(rows)}
