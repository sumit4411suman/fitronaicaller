"""Call job lifecycle with idempotent creation, eligibility gating, dispatch to a telecom route,
cancellation and emergency stop. States: pending -> queued -> dispatched -> in_progress -> completed|failed|cancelled,
or pending -> blocked when eligibility fails."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.db.models import Call, CallEvent, CallJob, Campaign, CampaignContact, Contact, PairedDevice
from sellagent_backend.security.tokens import generate_token, hash_token
from sellagent_backend.services import audit, eligibility, settings_service

_FINAL = {"completed", "failed", "cancelled", "blocked"}
_ALLOWED = {
    "pending": {"queued", "blocked", "cancelled"},
    "blocked": {"pending", "cancelled"},
    "queued": {"dispatched", "cancelled", "failed"},
    "dispatched": {"in_progress", "failed", "cancelled"},
    "in_progress": {"completed", "failed", "cancelled"},
}


class CallJobError(ValueError):
    pass


def _idem_key(contact_id: str, campaign_id: str | None, scheduled_for: datetime | None, explicit: str | None) -> str:
    if explicit:
        return explicit
    bucket = (scheduled_for or datetime.now(UTC)).strftime("%Y%m%d%H%M")
    return hashlib.sha256(f"{contact_id}|{campaign_id or ''}|{bucket}".encode()).hexdigest()[:40]


def create(
    session: Session, contact_id: str, *, campaign_id: str | None = None, mode: str | None = None, route: str = "manual",
    scheduled_for: datetime | None = None, idempotency_key: str | None = None, actor: str = "operator", device_id: str | None = None,
) -> CallJob:
    contact = session.get(Contact, contact_id)
    if contact is None:
        raise CallJobError("contact not found")
    campaign = session.get(Campaign, campaign_id) if campaign_id else None
    if campaign_id and campaign is None:
        raise CallJobError("campaign not found")
    mode = mode or (campaign.calling_mode if campaign else settings_service.get(session, "calling.default_mode"))
    key = _idem_key(contact_id, campaign_id, scheduled_for, idempotency_key)
    existing = session.scalar(select(CallJob).where(CallJob.idempotency_key == key))
    if existing:
        return existing  # idempotent: same request returns the same job
    open_job = session.scalar(select(CallJob).where(CallJob.contact_id == contact_id, CallJob.status.in_(("pending", "queued", "dispatched", "in_progress"))))
    if open_job:
        raise CallJobError(f"contact already has an open call job ({open_job.id}, {open_job.status})")
    device = session.get(PairedDevice, device_id) if device_id else None
    if device is None and route == "android_companion":
        device = session.scalar(select(PairedDevice).where(PairedDevice.status == "approved").order_by(PairedDevice.last_seen_at.desc()))
    result = eligibility.check(session, contact, campaign=campaign, mode=mode, route=route, device=device)
    job = CallJob(
        idempotency_key=key, contact_id=contact_id, campaign_id=campaign_id, phone_e164=contact.phone_e164, mode=mode,
        route=route, status="pending" if result.eligible else "blocked", scheduled_for=scheduled_for, authorized_by=actor,
        eligibility_result=result.to_dict(), device_id=device.id if device else None,
    )
    session.add(job)
    session.flush()
    if campaign:
        m = session.scalar(select(CampaignContact).where(CampaignContact.campaign_id == campaign.id, CampaignContact.contact_id == contact_id))
        if m and result.eligible:
            m.status = "queued"
    audit.record(session, "call_job.create", actor=actor, entity_type="call_job", entity_id=job.id, data={"status": job.status, "mode": mode, "route": route, "reasons": result.reasons})
    return job


def _transition(session: Session, job: CallJob, new_status: str, *, actor: str, note: str | None = None) -> CallJob:
    if new_status not in _ALLOWED.get(job.status, set()):
        raise CallJobError(f"call job cannot move from {job.status} to {new_status}")
    old = job.status
    job.status = new_status
    if new_status == "in_progress" and job.started_at is None:
        job.started_at = datetime.now(UTC)
    if new_status in _FINAL and new_status != "blocked":
        job.finished_at = datetime.now(UTC)
    if note:
        job.error = note
    session.flush()
    audit.record(session, f"call_job.{new_status}", actor=actor, entity_type="call_job", entity_id=job.id, data={"from": old, "note": note})
    return job


def queue(session: Session, job_id: str, *, actor: str = "operator") -> CallJob:
    """Re-check eligibility at queue time (state may have changed since creation)."""
    job = _get(session, job_id)
    if job.status == "blocked":
        job.status = "pending"
    contact = session.get(Contact, job.contact_id)
    campaign = session.get(Campaign, job.campaign_id) if job.campaign_id else None
    device = session.get(PairedDevice, job.device_id) if job.device_id else None
    assert contact is not None
    result = eligibility.check(session, contact, campaign=campaign, mode=job.mode, route=job.route, device=device)
    job.eligibility_result = result.to_dict()
    if not result.eligible:
        return _transition(session, job, "blocked", actor=actor, note="; ".join(result.reasons))
    return _transition(session, job, "queued", actor=actor)


def dispatch(session: Session, job_id: str, *, actor: str = "operator") -> tuple[CallJob, str]:
    """Mark the job dispatched and mint a one-time authorization token for the telecom route.
    Returns (job, plain_token). The token is only ever stored hashed."""
    job = _get(session, job_id)
    if settings_service.get(session, "calling.emergency_stop_active"):
        raise CallJobError("emergency stop is active")
    if job.status == "pending":
        job = queue(session, job_id, actor=actor)
        if job.status == "blocked":
            raise CallJobError("job is blocked: " + (job.error or "ineligible"))
    token = generate_token(24)
    job.authorization_token_hash = hash_token(token)
    _transition(session, job, "dispatched", actor=actor)
    call = Call(call_job_id=job.id, contact_id=job.contact_id, started_at=datetime.now(UTC))
    session.add(call)
    session.flush()
    session.add(CallEvent(call_id=call.id, event_type="dispatched", to_state="dial_request", source="backend", data={"route": job.route, "mode": job.mode}))
    contact = session.get(Contact, job.contact_id)
    if contact:
        contact.last_contact_at = datetime.now(UTC)
    session.flush()
    return job, token


def verify_authorization(session: Session, job_id: str, token: str) -> bool:
    job = session.get(CallJob, job_id)
    if job is None or not job.authorization_token_hash:
        return False
    return hash_token(token) == job.authorization_token_hash and job.status in ("dispatched", "in_progress")


def mark_in_progress(session: Session, job_id: str, *, actor: str = "device") -> CallJob:
    job = _get(session, job_id)
    if job.status == "in_progress":
        return job
    return _transition(session, job, "in_progress", actor=actor)


def complete(session: Session, job_id: str, *, outcome: str, detail: str | None = None, actor: str = "operator") -> CallJob:
    job = _get(session, job_id)
    if job.status in ("pending", "queued"):
        _transition(session, job, "dispatched", actor=actor)
    if job.status == "dispatched":
        _transition(session, job, "in_progress", actor=actor)
    job = _transition(session, job, "completed", actor=actor)
    call = session.scalar(select(Call).where(Call.call_job_id == job.id).order_by(Call.created_at.desc()))
    if call:
        call.outcome, call.outcome_detail, call.ended_at = outcome, detail, datetime.now(UTC)
        if call.started_at:
            call.duration_seconds = int((call.ended_at - call.started_at).total_seconds())
    if job.campaign_id:
        m = session.scalar(select(CampaignContact).where(CampaignContact.campaign_id == job.campaign_id, CampaignContact.contact_id == job.contact_id))
        if m:
            m.attempts += 1
            m.last_outcome = outcome
            m.status = "done" if outcome in ("converted", "not_interested", "opted_out", "wrong_number", "demo_scheduled") else "called"
    session.flush()
    return job


def fail(session: Session, job_id: str, *, reason: str, actor: str = "system") -> CallJob:
    job = _get(session, job_id)
    if job.status in _FINAL:
        return job
    if job.status == "pending":
        _transition(session, job, "queued", actor=actor)
    job = _transition(session, job, "failed", actor=actor, note=reason)
    call = session.scalar(select(Call).where(Call.call_job_id == job.id).order_by(Call.created_at.desc()))
    if call and call.outcome is None:
        call.outcome, call.outcome_detail, call.ended_at = "technical_failure", reason, datetime.now(UTC)
    return job


def cancel(session: Session, job_id: str, *, reason: str = "operator_cancel", actor: str = "operator") -> CallJob:
    job = _get(session, job_id)
    if job.status in _FINAL:
        return job
    job = _transition(session, job, "cancelled", actor=actor, note=reason)
    call = session.scalar(select(Call).where(Call.call_job_id == job.id).order_by(Call.created_at.desc()))
    if call and call.outcome is None:
        call.outcome, call.outcome_detail, call.ended_at = "cancelled", reason, datetime.now(UTC)
        session.add(CallEvent(call_id=call.id, event_type="cancelled", to_state="cancelled", source="backend", data={"reason": reason}))
    return job


def emergency_stop(session: Session, *, reason: str, actor: str = "operator", activate: bool = True) -> list[str]:
    """Activate the global stop and cancel every non-final job. Returns the cancelled job ids."""
    settings_service.set_value(session, "calling.emergency_stop_active", activate, actor=actor)
    cancelled: list[str] = []
    if activate:
        for job in session.scalars(select(CallJob).where(CallJob.status.in_(("pending", "queued", "dispatched", "in_progress")))):
            cancel(session, job.id, reason=f"emergency_stop:{reason}", actor=actor)
            cancelled.append(job.id)
    audit.record(session, "emergency_stop" if activate else "emergency_stop.cleared", actor=actor, severity="critical" if activate else "warning", data={"reason": reason, "cancelled": cancelled})
    return cancelled


def due_jobs(session: Session, now: datetime | None = None) -> list[CallJob]:
    now = now or datetime.now(UTC)
    return list(session.scalars(select(CallJob).where(CallJob.status.in_(("pending", "queued")), (CallJob.scheduled_for.is_(None)) | (CallJob.scheduled_for <= now)).order_by(CallJob.scheduled_for.nulls_first(), CallJob.created_at)))


def expire_stale(session: Session, *, older_than_minutes: int = 30) -> int:
    cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
    n = 0
    for job in session.scalars(select(CallJob).where(CallJob.status == "dispatched", CallJob.updated_at < cutoff)):
        fail(session, job.id, reason="dispatch timed out without device confirmation")
        n += 1
    return n


def _get(session: Session, job_id: str) -> CallJob:
    job = session.get(CallJob, job_id)
    if job is None:
        raise CallJobError("call job not found")
    return job


def to_dict(j: CallJob) -> dict[str, Any]:
    return {k: getattr(j, k) for k in ("id", "contact_id", "campaign_id", "phone_e164", "mode", "route", "status", "scheduled_for", "authorized_by", "eligibility_result", "attempt", "device_id", "error", "started_at", "finished_at", "created_at", "updated_at")}
