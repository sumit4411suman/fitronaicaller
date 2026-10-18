"""Analytics computed from real rows only. No invented numbers: every figure is a count/aggregate of stored data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sellagent_backend.db.models import Call, CallJob, Campaign, Contact, Followup


def dashboard(session: Session, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    day_ago, week_ago = now - timedelta(days=1), now - timedelta(days=7)
    total_contacts = session.scalar(select(func.count()).select_from(Contact).where(Contact.archived.is_(False))) or 0
    by_stage = {s: int(n) for s, n in session.execute(select(Contact.lead_stage, func.count()).where(Contact.archived.is_(False)).group_by(Contact.lead_stage))}
    calls_today = session.scalar(select(func.count()).select_from(Call).where(Call.started_at >= day_ago)) or 0
    calls_week = session.scalar(select(func.count()).select_from(Call).where(Call.started_at >= week_ago)) or 0
    outcomes = {o or "none": int(n) for o, n in session.execute(select(Call.outcome, func.count()).where(Call.started_at >= week_ago).group_by(Call.outcome))}
    connected = sum(n for o, n in outcomes.items() if o not in ("none", "no_answer", "busy", "technical_failure", "cancelled"))
    followups_due = session.scalar(select(func.count()).select_from(Followup).where(Followup.status == "open", Followup.due_at <= now + timedelta(days=1))) or 0
    overdue = session.scalar(select(func.count()).select_from(Followup).where(Followup.status == "open", Followup.due_at < now)) or 0
    queue = {s: int(n) for s, n in session.execute(select(CallJob.status, func.count()).group_by(CallJob.status))}
    campaigns = {s: int(n) for s, n in session.execute(select(Campaign.status, func.count()).group_by(Campaign.status))}
    daily: list[dict[str, Any]] = []
    for i in range(6, -1, -1):
        start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        n = session.scalar(select(func.count()).select_from(Call).where(Call.started_at >= start, Call.started_at < end)) or 0
        daily.append({"date": start.date().isoformat(), "calls": int(n)})
    return {
        "generated_at": now, "contacts_total": int(total_contacts), "contacts_by_stage": by_stage, "calls_today": int(calls_today),
        "calls_week": int(calls_week), "outcomes_week": outcomes, "connect_rate_week": (connected / calls_week) if calls_week else None,
        "followups_due_24h": int(followups_due), "followups_overdue": int(overdue), "call_queue": queue, "campaigns": campaigns,
        "calls_daily": daily, "data_source": "live_database",
    }


def call_history(session: Session, *, limit: int = 100, offset: int = 0, contact_id: str | None = None, outcome: str | None = None) -> tuple[list[dict[str, Any]], int]:
    q = select(Call, Contact.business_name, Contact.phone_e164).join(Contact, Contact.id == Call.contact_id)
    if contact_id:
        q = q.where(Call.contact_id == contact_id)
    if outcome:
        q = q.where(Call.outcome == outcome)
    total = session.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = session.execute(q.order_by(Call.created_at.desc()).limit(min(limit, 500)).offset(offset)).all()
    out = []
    for call, name, phone in rows:
        out.append({
            "id": call.id, "call_job_id": call.call_job_id, "contact_id": call.contact_id, "business_name": name, "phone_e164": phone,
            "conversation_state": call.conversation_state, "language": call.language, "outcome": call.outcome, "outcome_detail": call.outcome_detail,
            "started_at": call.started_at, "connected_at": call.connected_at, "ended_at": call.ended_at, "duration_seconds": call.duration_seconds,
            "audio_route": call.audio_route, "recorded": call.recorded,
        })
    return out, int(total)


def campaign_report(session: Session, campaign_id: str) -> dict[str, Any]:
    jobs = {s: int(n) for s, n in session.execute(select(CallJob.status, func.count()).where(CallJob.campaign_id == campaign_id).group_by(CallJob.status))}
    outcomes = {o or "none": int(n) for o, n in session.execute(select(Call.outcome, func.count()).join(CallJob, CallJob.id == Call.call_job_id).where(CallJob.campaign_id == campaign_id).group_by(Call.outcome))}
    return {"campaign_id": campaign_id, "jobs": jobs, "outcomes": outcomes}
