"""Android companion route: dial via the paired phone over the authenticated WebSocket. Capability flags are
read from what the device itself reported and from stored real-device audio test results. Nothing here can
capture or inject cellular call audio; those flags only turn true if the device proved it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sellagent_protocol import CallRequest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sellagent_backend.db.models import AudioTest, PairedDevice
from sellagent_backend.telecom.base import RouteCapabilities
from sellagent_backend.ws.hub import Hub


def audio_gate_status(session: Session, device_id: str | None = None) -> dict:
    """Both directions must have an operator-confirmed real-device PASS for the gate to open."""
    q = select(AudioTest).where(AudioTest.kind == "real_device", AudioTest.operator_confirmed.is_(True), AudioTest.status == "pass")
    if device_id:
        q = q.where(AudioTest.device_id == device_id)
    rows = list(session.scalars(q))
    inbound = [r for r in rows if r.direction in ("inbound", "both")]
    outbound = [r for r in rows if r.direction in ("outbound", "both")]
    return {
        "remote_audio_capture_verified": bool(inbound), "audio_injection_verified": bool(outbound),
        "allowed": bool(inbound) and bool(outbound),
        "evidence": {"inbound": [r.test_id for r in inbound], "outbound": [r.test_id for r in outbound]},
    }


class AndroidCompanionAdapter:
    route = "android_companion"

    def __init__(self, hub: Hub, session_factory: sessionmaker[Session]) -> None:
        self.hub = hub
        self._sf = session_factory

    def capabilities(self, device_id: str | None = None) -> RouteCapabilities:
        with self._sf() as s:
            dev = s.get(PairedDevice, device_id) if device_id else s.scalar(select(PairedDevice).where(PairedDevice.status == "approved").order_by(PairedDevice.last_seen_at.desc()))
            caps = (dev.capabilities if dev else {}) or {}
            gate = audio_gate_status(s, dev.id if dev else None)
        notes = []
        if dev is None:
            notes.append("no approved Android device paired")
        elif not self.hub.is_connected(dev.id):
            notes.append("device paired but not connected")
        if not gate["allowed"]:
            notes.append("two-way cellular audio NOT verified on a real device; autonomous mode blocked")
        return RouteCapabilities(
            route=self.route, can_dial=bool(caps.get("can_place_calls")) and dev is not None, reports_call_state=bool(caps.get("reports_call_state")),
            remote_audio_capture=gate["remote_audio_capture_verified"], audio_injection=gate["audio_injection_verified"], autonomous_supported=gate["allowed"], notes=notes,
        )

    async def dial(self, *, call_job_id: str, e164: str, display_name: str | None, mode: str, authorization_token: str, language: str, device_id: str | None) -> tuple[bool, str]:
        if device_id is None:
            return False, "no device selected"
        if not self.hub.is_connected(device_id):
            return False, "device is not connected"
        req = CallRequest(call_job_id=call_job_id, e164_number=e164, display_name=display_name, mode=mode, authorization_token=authorization_token, language=language, expires_at=datetime.now(UTC) + timedelta(minutes=2))  # type: ignore[arg-type]
        return await self.hub.request_call(device_id, req)

    async def cancel(self, *, call_job_id: str, device_id: str | None, reason: str) -> bool:
        if device_id is None:
            return False
        return await self.hub.cancel_call(device_id, call_job_id, reason)
