"""WebSocket hub: authenticated device and desktop connections, message de-duplication, call-state routing,
heartbeats, emergency stop fan-out and reconnection support."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sellagent_backend.db.models import AudioTest, Call, CallEvent, CallJob, PairedDevice
from sellagent_backend.services import audit, call_jobs, settings_service
from sellagent_protocol import (
    AudioTestEvent,
    AudioTestResult,
    CallRequest,
    CallState,
    CallStateEvent,
    DeviceCapabilities,
    EmergencyStop,
    Envelope,
    ErrorEvent,
    Heartbeat,
    HeartbeatAck,
    MessageType,
    ReconnectRequest,
    ReconnectResponse,
)
from sellagent_protocol.messages import Ack

log = logging.getLogger("sellagent.ws")

_STATE_MAP = {
    CallState.DIALING: "dialing", CallState.RINGING: "ringing", CallState.ACTIVE: "connected", CallState.OFFHOOK: "connected",
    CallState.HOLDING: "connected", CallState.DISCONNECTED: "disconnected", CallState.FAILED: "technical_failure",
    CallState.REJECTED: "cancelled", CallState.IDLE: "disconnected", CallState.UNKNOWN: "unknown", CallState.REQUESTED: "dial_request",
}


class _LRU:
    def __init__(self, cap: int = 5000) -> None:
        self._d: OrderedDict[str, None] = OrderedDict()
        self._cap = cap

    def seen(self, key: str) -> bool:
        if key in self._d:
            self._d.move_to_end(key)
            return True
        self._d[key] = None
        if len(self._d) > self._cap:
            self._d.popitem(last=False)
        return False


class Hub:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory
        self._devices: dict[str, WebSocket] = {}
        self._desktops: set[WebSocket] = set()
        self._seen = _LRU()
        self._pending_acks: dict[str, asyncio.Future[Any]] = {}
        self._outbox: dict[str, list[Envelope]] = {}  # per device, replayed on reconnect
        self.listeners: list[Callable[[Envelope], None]] = []
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ registry
    async def register_device(self, device_id: str, ws: WebSocket) -> None:
        async with self._lock:
            old = self._devices.get(device_id)
            self._devices[device_id] = ws
        if old is not None and old is not ws:
            try:
                await old.close(code=4000, reason="replaced by a new connection")
            except Exception:  # noqa: BLE001
                pass
        await self.broadcast_desktop(Envelope(type=MessageType.HEARTBEAT, payload=Heartbeat(device_id=device_id, network="unknown").model_dump(mode="json")))

    async def unregister_device(self, device_id: str, ws: WebSocket) -> None:
        async with self._lock:
            if self._devices.get(device_id) is ws:
                del self._devices[device_id]
        await self.broadcast_desktop(Envelope(type=MessageType.ERROR, payload=ErrorEvent(code="device_disconnected", message=f"device {device_id} disconnected", retryable=True).model_dump(mode="json")))

    def register_desktop(self, ws: WebSocket) -> None:
        self._desktops.add(ws)

    def unregister_desktop(self, ws: WebSocket) -> None:
        self._desktops.discard(ws)

    def connected_devices(self) -> list[str]:
        return list(self._devices)

    def is_connected(self, device_id: str) -> bool:
        return device_id in self._devices

    # ------------------------------------------------------------------ sending
    async def broadcast_desktop(self, env: Envelope) -> None:
        for cb in list(self.listeners):
            try:
                cb(env)
            except Exception:  # noqa: BLE001
                log.exception("listener failed")
        dead = []
        for ws in list(self._desktops):
            try:
                await ws.send_text(env.model_dump_json())
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self._desktops.discard(ws)

    async def send_to_device(self, device_id: str, env: Envelope, *, queue_if_offline: bool = False) -> bool:
        ws = self._devices.get(device_id)
        if ws is None:
            if queue_if_offline:
                self._outbox.setdefault(device_id, []).append(env)
            return False
        try:
            await ws.send_text(env.model_dump_json())
            return True
        except Exception:  # noqa: BLE001
            if queue_if_offline:
                self._outbox.setdefault(device_id, []).append(env)
            return False

    async def send_and_wait_ack(self, device_id: str, env: Envelope, timeout: float = 10.0) -> Envelope | None:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending_acks[env.message_id] = fut
        try:
            if not await self.send_to_device(device_id, env):
                return None
            return await asyncio.wait_for(fut, timeout)
        except TimeoutError:
            return None
        finally:
            self._pending_acks.pop(env.message_id, None)

    async def request_call(self, device_id: str, req: CallRequest) -> tuple[bool, str]:
        env = Envelope.of(MessageType.CALL_REQUEST, req)
        reply = await self.send_and_wait_ack(device_id, env, timeout=10.0)
        if reply is None:
            return False, "device did not acknowledge the call request within 10 s"
        if reply.type == MessageType.ERROR:
            return False, ErrorEvent.model_validate(reply.payload).message
        return True, "acknowledged"

    async def cancel_call(self, device_id: str, call_job_id: str, reason: str) -> bool:
        from sellagent_protocol import CancelRequest

        return await self.send_to_device(device_id, Envelope.of(MessageType.CALL_CANCEL, CancelRequest(call_job_id=call_job_id, reason=reason)), queue_if_offline=True)

    async def emergency_stop(self, *, reason: str, issued_by: str = "windows", actor: str = "operator") -> list[str]:
        with self._sf() as s:
            cancelled = call_jobs.emergency_stop(s, reason=reason, actor=actor, activate=True)
            s.commit()
        env = Envelope.of(MessageType.EMERGENCY_STOP, EmergencyStop(reason=reason, issued_by=issued_by))  # type: ignore[arg-type]
        for dev_id in list(self._devices):
            await self.send_to_device(dev_id, env, queue_if_offline=True)
        await self.broadcast_desktop(env)
        return cancelled

    async def clear_emergency_stop(self, *, actor: str = "operator") -> None:
        with self._sf() as s:
            call_jobs.emergency_stop(s, reason="cleared by operator", actor=actor, activate=False)
            s.commit()
        await self.broadcast_desktop(Envelope(type=MessageType.ACK, payload=Ack(message_id="emergency_stop_cleared").model_dump()))

    # ------------------------------------------------------------------ inbound from device
    async def handle_device_message(self, device: PairedDevice, raw: str) -> Envelope | None:
        """Validate, de-duplicate and process one device message. Returns a reply envelope (or None)."""
        from pydantic import ValidationError

        from sellagent_protocol import parse_envelope

        try:
            env, payload = parse_envelope(raw)
        except ValidationError as exc:
            return Envelope(type=MessageType.ERROR, payload=ErrorEvent(code="invalid_message", message=str(exc)[:900]).model_dump(mode="json"))
        if self._seen.seen(env.message_id):
            return Envelope(type=MessageType.ACK, payload=Ack(message_id=env.message_id).model_dump(), in_reply_to=env.message_id)
        if env.in_reply_to and env.in_reply_to in self._pending_acks:
            fut = self._pending_acks[env.in_reply_to]
            if not fut.done():
                fut.set_result(env)
            if env.type in (MessageType.ACK, MessageType.ERROR):
                return None
        with self._sf() as s:
            dev = s.get(PairedDevice, device.id)
            assert dev is not None
            dev.last_seen_at = datetime.now(UTC)
            reply: Envelope | None = None
            if isinstance(payload, Heartbeat):
                if payload.capabilities:
                    dev.capabilities = payload.capabilities.model_dump()
                reply = Envelope.of(MessageType.HEARTBEAT_ACK, HeartbeatAck(emergency_stop_active=bool(settings_service.get(s, "calling.emergency_stop_active"))), in_reply_to=env.message_id)
            elif isinstance(payload, DeviceCapabilities):
                dev.capabilities = payload.model_dump()
                audit.record(s, "device.capabilities", actor=dev.id, entity_type="device", entity_id=dev.id, data=payload.model_dump())
                reply = Envelope(type=MessageType.ACK, payload=Ack(message_id=env.message_id).model_dump(), in_reply_to=env.message_id)
            elif isinstance(payload, CallStateEvent):
                self._apply_call_state(s, dev, env, payload)
                reply = Envelope(type=MessageType.ACK, payload=Ack(message_id=env.message_id).model_dump(), in_reply_to=env.message_id)
            elif isinstance(payload, AudioTestResult):
                s.add(AudioTest(
                    test_id=payload.test_id, device_id=dev.id, step=payload.step, direction=payload.direction.value, status=payload.status, kind="real_device",
                    route=payload.route.value if payload.route else None, api_used=payload.api_used, phone_model=dev.model, android_version=dev.android_version,
                    app_version=dev.app_version, error_message=payload.error_message, metrics=dict(payload.metrics), evidence=dict(payload.evidence), operator_confirmed=False,
                    actual=payload.error_message or payload.status,
                ))
                audit.record(s, "audio_test.result", actor=dev.id, entity_type="audio_test", entity_id=payload.test_id, data={"step": payload.step, "status": payload.status})
                reply = Envelope(type=MessageType.ACK, payload=Ack(message_id=env.message_id).model_dump(), in_reply_to=env.message_id)
            elif isinstance(payload, AudioTestEvent):
                reply = None
            elif isinstance(payload, EmergencyStop):
                s.commit()
                await self.emergency_stop(reason=payload.reason, issued_by="android", actor=dev.id)
                reply = Envelope(type=MessageType.EMERGENCY_STOP_ACK, payload=Ack(message_id=env.message_id).model_dump(), in_reply_to=env.message_id)
            elif isinstance(payload, ReconnectRequest):
                pending = self._outbox.pop(dev.id, [])
                reply = Envelope.of(MessageType.RECONNECT_RESPONSE, ReconnectResponse(accepted=True, emergency_stop_active=bool(settings_service.get(s, "calling.emergency_stop_active")), message=f"{len(pending)} queued message(s) will follow"), in_reply_to=env.message_id)
                for queued in pending:
                    await self.send_to_device(dev.id, queued)
            elif isinstance(payload, ErrorEvent):
                audit.record(s, "device.error", actor=dev.id, entity_type="device", entity_id=dev.id, severity="warning", data={"code": payload.code, "message": payload.message})
                reply = None
            else:
                reply = Envelope(type=MessageType.ERROR, payload=ErrorEvent(code="unexpected_message", message=f"{env.type} is not accepted from devices").model_dump(mode="json"), in_reply_to=env.message_id)
            s.commit()
        await self.broadcast_desktop(env)
        return reply

    def _apply_call_state(self, s: Session, dev: PairedDevice, env: Envelope, ev: CallStateEvent) -> None:
        job = s.get(CallJob, ev.call_job_id)
        if job is None:
            return
        call = s.scalar(select(Call).where(Call.call_job_id == job.id).order_by(Call.created_at.desc()))
        if call is None:
            return
        if s.scalar(select(CallEvent.id).where(CallEvent.call_id == call.id, CallEvent.message_id == env.message_id)):
            return  # duplicate event
        to_state = _STATE_MAP.get(ev.state, "unknown")
        s.add(CallEvent(call_id=call.id, occurred_at=ev.occurred_at, event_type=f"device.{ev.state.value}", from_state=call.conversation_state, to_state=to_state, source=ev.source, message_id=env.message_id, data={"route": ev.audio_route.value if ev.audio_route else None, "cause": ev.disconnect_cause, "detail": ev.detail, "device_id": dev.id}))
        if ev.audio_route:
            call.audio_route = ev.audio_route.value
        if ev.state in (CallState.DIALING, CallState.RINGING):
            call.conversation_state = to_state
            if job.status == "dispatched":
                call_jobs.mark_in_progress(s, job.id, actor=dev.id)
        elif ev.state in (CallState.ACTIVE, CallState.OFFHOOK):
            call.conversation_state = "connected"
            call.connected_at = call.connected_at or ev.occurred_at
            if job.status == "dispatched":
                call_jobs.mark_in_progress(s, job.id, actor=dev.id)
        elif ev.state in (CallState.DISCONNECTED, CallState.IDLE):
            if job.status in ("dispatched", "in_progress") and call.outcome is None:
                cause = (ev.disconnect_cause or "").lower()
                if call.connected_at is None:
                    outcome = "busy" if "busy" in cause else "no_answer"
                    call_jobs.complete(s, job.id, outcome=outcome, detail=ev.disconnect_cause, actor=dev.id)
                else:
                    call.ended_at = ev.occurred_at
                    call.conversation_state = "completed" if call.conversation_state not in ("opted_out",) else call.conversation_state
                    # outcome is set by the operator / conversation engine; keep job in_progress until outcome recorded
        elif ev.state == CallState.FAILED:
            call_jobs.fail(s, job.id, reason=ev.disconnect_cause or ev.detail or "device reported failure", actor=dev.id)
        elif ev.state == CallState.REJECTED:
            call_jobs.fail(s, job.id, reason="device refused to dial: " + (ev.detail or "unspecified"), actor=dev.id)

    # ------------------------------------------------------------------ housekeeping
    def stale_devices(self, *, seconds: int = 90) -> list[str]:
        cutoff = datetime.now(UTC) - timedelta(seconds=seconds)
        with self._sf() as s:
            return [d.id for d in s.scalars(select(PairedDevice).where(PairedDevice.status == "approved", PairedDevice.last_seen_at < cutoff))]
