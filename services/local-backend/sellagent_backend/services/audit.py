"""Append-only audit log for sensitive actions. Never log secrets: callers pass structured data and
``redact`` strips well-known secret keys defensively."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from sellagent_backend.db.models import AuditEvent

_SECRET_KEYS = {"token", "device_token", "authorization_token", "password", "secret", "pairing_code", "api_key"}


def redact(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return data
    out: dict[str, Any] = {}
    for k, v in data.items():
        if any(s in k.lower() for s in _SECRET_KEYS):
            out[k] = "[REDACTED]"
        elif isinstance(v, dict):
            out[k] = redact(v)
        else:
            out[k] = v
    return out


def record(
    session: Session,
    action: str,
    *,
    actor: str = "operator",
    entity_type: str | None = None,
    entity_id: str | None = None,
    severity: str = "info",
    request_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> AuditEvent:
    ev = AuditEvent(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        severity=severity,
        request_id=request_id,
        data=redact(data),
    )
    session.add(ev)
    session.flush()
    return ev
