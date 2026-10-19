"""Exotel AgentStream WebSocket endpoint. Exotel (via an authenticated tunnel) connects here and streams the live
call audio both ways. Token-authenticated; never expose it unauthenticated. The audio is bridged into the bound
call's ExotelStreamTransport, which the autonomous loop consumes - all AI stays local.

Protocol (AgentStream Voicebot, confirm field names against your account): inbound JSON events ``connected`` /
``start`` (carries the call id we tagged) / ``media`` (base64 PCM) / ``stop``; outbound ``media`` events play
audio to the caller and ``clear`` flushes queued audio on barge-in.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from sellagent_backend.telecom.exotel import decode_media_event, encode_media_event

log = logging.getLogger("sellagent.exotel")
router = APIRouter(prefix="/exotel", tags=["exotel"])


def _authorized(ws: WebSocket) -> bool:
    expected = os.getenv("EXOTEL_STREAM_TOKEN", "")
    if not expected:
        return False  # fail closed: no token configured => no stream accepted
    got = ws.query_params.get("token") or ws.headers.get("x-stream-token", "")
    return bool(got) and got == expected


@router.websocket("/stream")
async def exotel_stream(ws: WebSocket) -> None:
    if not _authorized(ws):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="missing or invalid stream token")
        return
    provider = ws.app.state.telecom.get("exotel")
    if provider is None:
        await ws.close(code=status.WS_1011_INTERNAL_ERROR, reason="exotel provider unavailable")
        return
    await ws.accept()
    from sellagent_backend.telecom.exotel import ExotelStreamTransport

    call_id = ws.query_params.get("call_id")
    rate = int(ws.query_params.get("sample-rate", "8000") or "8000")
    transport: ExotelStreamTransport | None = None
    stream_sid = ""

    async def writer() -> None:
        # Play AI audio back to the caller, and flush on barge-in.
        while transport is not None and transport.is_connected():
            if transport.take_clear():
                try:
                    await ws.send_text(json.dumps({"event": "clear", "stream_sid": stream_sid}))
                except Exception:  # noqa: BLE001, S112
                    return
            for frame in transport.drain_outbound():
                try:
                    await ws.send_text(json.dumps(encode_media_event(frame, stream_sid)))
                except Exception:  # noqa: BLE001, S112
                    return
            await asyncio.sleep(0.02)

    writer_task: asyncio.Task | None = None
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:  # noqa: BLE001, S112
                continue
            event = msg.get("event")
            if event in ("connected", "start"):
                cid = call_id or msg.get("call_id") or (msg.get("start") or {}).get("custom_field") or msg.get("custom_field")
                stream_sid = msg.get("stream_sid") or (msg.get("start") or {}).get("stream_sid") or stream_sid
                resolved = provider.resolve_call(cid or "")
                if resolved is None:
                    await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="unknown call id")
                    return
                transport = ExotelStreamTransport(sample_rate=rate)
                provider.bind(resolved, transport)
                call_id = resolved
                writer_task = asyncio.create_task(writer())
                log.info("Exotel stream bound to call %s (%d Hz)", resolved, rate)
            elif event == "media" and transport is not None:
                pcm = decode_media_event(msg)
                if pcm:
                    transport.feed_inbound(pcm)
            elif event == "stop":
                break
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("Exotel stream error")
    finally:
        if transport is not None:
            transport.close()
        if writer_task is not None:
            writer_task.cancel()
        if call_id:
            provider.unbind(call_id)
        try:
            await ws.close()
        except Exception:  # noqa: BLE001, S110
            pass
