"""WebSocket endpoints. Device: token in the first message or `Authorization` header. Desktop: local token."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from sellagent_backend.db.models import PairedDevice
from sellagent_backend.security.tokens import hash_token, is_expired, tokens_match
from sellagent_protocol import Envelope, ErrorEvent, MessageType

log = logging.getLogger("sellagent.ws")
router = APIRouter(prefix="/ws", tags=["websocket"])


def _token_from(ws: WebSocket) -> str | None:
    auth = ws.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ws.headers.get("x-device-token") or ws.headers.get("x-local-token") or ws.query_params.get("token")


@router.websocket("/device")
async def device_ws(ws: WebSocket) -> None:
    token = _token_from(ws)
    if not token:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="missing token")
        return
    sf = ws.app.state.session_factory
    with sf() as s:
        dev = s.scalar(select(PairedDevice).where(PairedDevice.token_hash == hash_token(token)))
        if dev is None or dev.status != "approved" or is_expired(dev.token_expires_at):
            await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid token")
            return
        dev.last_seen_at = datetime.now(UTC)
        dev.last_ip = ws.client.host if ws.client else None
        s.commit()
        device_id = dev.id
        s.expunge(dev)
    await ws.accept(subprotocol=None)
    hub = ws.app.state.hub
    await hub.register_device(device_id, ws)
    try:
        while True:
            raw = await ws.receive_text()
            if len(raw) > 64_000:
                await ws.send_text(Envelope(type=MessageType.ERROR, payload=ErrorEvent(code="too_large", message="message exceeds 64 KB").model_dump(mode="json")).model_dump_json())
                continue
            reply = await hub.handle_device_message(dev, raw)
            if reply is not None:
                await ws.send_text(reply.model_dump_json())
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("device websocket error")
    finally:
        await hub.unregister_device(device_id, ws)


@router.websocket("/desktop")
async def desktop_ws(ws: WebSocket) -> None:
    token = _token_from(ws)
    if not token or not tokens_match(token, ws.app.state.local_token_hash):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid local token")
        return
    await ws.accept()
    hub = ws.app.state.hub
    hub.register_desktop(ws)
    try:
        while True:
            raw = await ws.receive_text()
            # Desktop may send emergency stop over the socket for lowest latency
            try:
                env = Envelope.model_validate_json(raw)
            except Exception:  # noqa: BLE001
                continue
            if env.type == MessageType.EMERGENCY_STOP:
                from sellagent_protocol import EmergencyStop

                es = EmergencyStop.model_validate(env.payload)
                await hub.emergency_stop(reason=es.reason, issued_by="windows")
    except WebSocketDisconnect:
        pass
    finally:
        hub.unregister_desktop(ws)
