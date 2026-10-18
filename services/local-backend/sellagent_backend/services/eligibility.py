"""Pre-call eligibility: every outbound promotional call must pass all checks. The result is stored on
the call job so the decision is auditable. The LLM has no way to influence this module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sellagent_backend.db.models import CallJob, Campaign, Contact, PairedDevice
from sellagent_backend.services import settings_service, suppression
from sellagent_backend.services.phone import number_type


@dataclass
class EligibilityResult:
    eligible: bool
    reasons: list[str] = field(default_factory=list)  # blocking reasons
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {"eligible": self.eligible, "reasons": self.reasons, "warnings": self.warnings, "checks": self.checks, "checked_at": self.checked_at.isoformat()}


def _parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def in_quiet_hours(now_local: datetime, start: str, end: str) -> bool:
    sh, sm = _parse_hhmm(start)
    eh, em = _parse_hhmm(end)
    t = now_local.hour * 60 + now_local.minute
    s, e = sh * 60 + sm, eh * 60 + em
    if s == e:
        return False
    if s < e:
        return s <= t < e
    return t >= s or t < e  # wraps midnight


def check(
    session: Session, contact: Contact, *, campaign: Campaign | None = None, mode: str = "human_assisted",
    route: str = "manual", device: PairedDevice | None = None, now: datetime | None = None,
) -> EligibilityResult:
    now = now or datetime.now(UTC)
    s = settings_service.get_all(session)
    res = EligibilityResult(eligible=True)
    tz = ZoneInfo(s.get("general.timezone") or "Asia/Kolkata")
    now_local = now.astimezone(tz)

    # 1. emergency stop
    if s["calling.emergency_stop_active"]:
        res.reasons.append("emergency stop is active")
    res.checks["emergency_stop"] = s["calling.emergency_stop_active"]

    # 2. number validity & type
    nt = number_type(contact.phone_e164)
    res.checks["number_type"] = nt
    if nt in ("premium_rate", "toll_free"):
        res.reasons.append(f"number type {nt} is not callable for sales")
    if contact.archived:
        res.reasons.append("contact is archived")

    # 3. suppression / opt-out
    sup = suppression.is_suppressed(session, contact.phone_e164)
    res.checks["suppressed"] = bool(sup)
    if sup:
        res.reasons.append(f"number is on the suppression list ({sup.reason})")
    if contact.opted_out:
        res.reasons.append("contact has opted out")

    # 4. consent
    require_consent = campaign.requires_consent if campaign else bool(s["calling.require_consent"])
    res.checks["consent_status"] = contact.consent_status
    res.checks["consent_required"] = require_consent
    if require_consent and contact.consent_status != "granted":
        res.reasons.append(f"consent not granted (status: {contact.consent_status})")
    elif not require_consent and contact.consent_status != "granted":
        res.warnings.append("calling without recorded consent; verify this is lawful for this campaign")
    if contact.source_verification == "rejected":
        res.reasons.append("contact source was rejected during verification")
    elif contact.source_verification == "unverified":
        res.warnings.append("contact source is unverified")

    # 5. campaign authorisation
    if campaign is not None:
        res.checks["campaign_status"] = campaign.status
        if campaign.status not in ("authorized", "active"):
            res.reasons.append(f"campaign is not authorized (status: {campaign.status})")
        if campaign.starts_at and now < campaign.starts_at:
            res.reasons.append("campaign has not started")
        if campaign.ends_at and now > campaign.ends_at:
            res.reasons.append("campaign has ended")
    elif mode == "autonomous":
        res.reasons.append("autonomous calls require an authorized campaign")

    # 6. quiet hours
    qs = (campaign.quiet_hours_start if campaign and campaign.quiet_hours_start else s["calling.quiet_hours_start"])
    qe = (campaign.quiet_hours_end if campaign and campaign.quiet_hours_end else s["calling.quiet_hours_end"])
    quiet = in_quiet_hours(now_local, qs, qe)
    res.checks["quiet_hours"] = {"start": qs, "end": qe, "local_time": now_local.strftime("%H:%M"), "in_quiet_hours": quiet}
    if quiet:
        res.reasons.append(f"within quiet hours ({qs}-{qe} local)")

    # 7. rate limits
    hour_ago, day_start = now - timedelta(hours=1), now_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    active_statuses = ("queued", "dispatched", "in_progress", "completed", "failed")
    per_hour = session.scalar(select(func.count()).select_from(CallJob).where(CallJob.status.in_(active_statuses), CallJob.created_at >= hour_ago)) or 0
    per_day = session.scalar(select(func.count()).select_from(CallJob).where(CallJob.status.in_(active_statuses), CallJob.created_at >= day_start)) or 0
    last = session.scalar(select(func.max(CallJob.created_at)).where(CallJob.status.in_(active_statuses)))
    res.checks["rate"] = {"last_hour": per_hour, "today": per_day}
    if per_hour >= int(s["calling.max_calls_per_hour"]):
        res.reasons.append("hourly call limit reached")
    if per_day >= int(s["calling.max_calls_per_day"]):
        res.reasons.append("daily call limit reached")
    if campaign and per_day >= campaign.max_calls_per_day:
        res.reasons.append("campaign daily limit reached")
    if last is not None and (now - last).total_seconds() < int(s["calling.min_seconds_between_calls"]):
        res.reasons.append("minimum spacing between calls not elapsed")

    # 8. attempts per contact
    attempts = session.scalar(select(func.count()).select_from(CallJob).where(CallJob.contact_id == contact.id, CallJob.status.in_(active_statuses))) or 0
    res.checks["attempts"] = attempts
    max_attempts = campaign.max_attempts_per_contact if campaign else 3
    if attempts >= max_attempts:
        res.reasons.append(f"maximum attempts ({max_attempts}) reached for this contact")

    # 9. mode & route support
    res.checks["mode"] = mode
    res.checks["route"] = route
    if mode == "autonomous":
        if not s["release_gate.autonomous_calling_allowed"]:
            res.reasons.append("autonomous mode blocked by release gate (no real-device two-way audio evidence)")
        if not s["calling.autonomous_enabled"]:
            res.reasons.append("autonomous mode not enabled in settings")
    if route == "android_companion":
        if device is None or device.status != "approved":
            res.reasons.append("no approved Android companion device")
        else:
            caps = device.capabilities or {}
            if not caps.get("can_place_calls"):
                res.reasons.append("paired device has not reported call-placement capability")
            if mode == "autonomous" and not (caps.get("remote_audio_capture_verified") and caps.get("audio_injection_verified")):
                res.reasons.append("paired device has not verified two-way call audio")
    elif route == "media_gateway":
        if not s["gateway.enabled"]:
            res.reasons.append("external audio gateway is not configured (Settings: gateway.*)")
        if mode == "autonomous" and not s["release_gate.autonomous_calling_allowed"]:
            res.reasons.append("autonomous mode blocked by release gate (no real-device two-way audio evidence)")
    elif route != "manual":
        res.reasons.append(f"unsupported calling route {route!r}")

    res.eligible = not res.reasons
    return res
