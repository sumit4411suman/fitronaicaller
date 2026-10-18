"""Real-time transcription over WebSocket (PC microphone or line-in during a human-assisted call).

Client -> server: binary frames of PCM16 little-endian mono 16 kHz audio (any frame size); text frames
{"type":"stop"} or {"type":"speaker","speaker":"prospect|operator"}.
Server -> client: {"type":"ready"}, {"type":"vad","speech":true}, {"type":"final","seq","text","language","sentiment"},
{"type":"error","code","error"}.

Gates (all required): signed-in role with calls:write; settings privacy.allow_live_transcription = true; the call is
live; the operator recorded the prospect's transcription consent (POST /calls/{id}/transcription-consent).
Audio is processed in memory and discarded; only the text is stored as transcript lines (source "stt").
"""

from __future__ import annotations

import asyncio
import json
import logging

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import func, select

from sellagent_backend.db.models import Call, Transcript
from sellagent_backend.services import settings_service

log = logging.getLogger("sellagent.transcribe")
router = APIRouter(prefix="/ws", tags=["websocket"])

SR = 16000
FRAME = int(SR * 0.03)  # 30 ms
MAX_SEGMENT_S = 15.0
LIVE_STATES = {"connected", "greeting", "permission_to_continue", "needs_discovery", "product_explanation", "objection_handling", "demo_invitation", "human_handoff", "followup_scheduling"}


def get_stt(app_state: object, model: str) -> object:
    eng = getattr(app_state, "stt_engine", None)
    if eng is None or getattr(eng, "model_size", model) != model:
        from sellagent_speech import FasterWhisperSTT

        eng = FasterWhisperSTT(model, models_dir=app_state.settings.models_dir)  # type: ignore[attr-defined]
        app_state.stt_engine = eng  # type: ignore[attr-defined]
    return eng


@router.websocket("/transcribe")
async def transcribe_ws(ws: WebSocket) -> None:
    from sellagent_speech.vad import EnergyVAD, VadConfig

    from sellagent_backend.api.deps import resolve_principal
    from sellagent_backend.api.v1.ws import _token_from

    st = ws.app.state
    principal = resolve_principal(st, _token_from(ws))
    if principal is None or not principal.can("calls:write"):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="not authorised for calls:write")
        return
    call_id = ws.query_params.get("call_id", "")
    language = ws.query_params.get("language", "auto")
    speaker = ws.query_params.get("speaker", "prospect")
    with st.session_factory() as s:
        call = s.get(Call, call_id)
        reason = None
        if not settings_service.get(s, "privacy.allow_live_transcription"):
            reason = "live transcription is disabled in privacy settings"
        elif call is None:
            reason = "call not found"
        elif call.conversation_state not in LIVE_STATES:
            reason = f"call is not live ({call.conversation_state})"
        elif call.transcription_consent_at is None:
            reason = "record the prospect's transcription consent first"
        allow_dl = bool(st.settings.allow_external_network) or bool(settings_service.get(s, "privacy.allow_external_network"))
        model = settings_service.get(s, "ai.whisper_model")
    await ws.accept()
    if reason:
        await ws.send_text(json.dumps({"type": "error", "code": "not_allowed", "error": reason}))
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    stt = get_stt(st, model)
    ok, msg = stt.available()  # type: ignore[attr-defined]
    if not ok:
        await ws.send_text(json.dumps({"type": "error", "code": "stt_unavailable", "error": msg}))
        await ws.close()
        return
    await ws.send_text(json.dumps({"type": "ready", "sample_rate": SR, "format": "pcm_s16le_mono", "model": model, "audio_stored": False}))
    vad = EnergyVAD(VadConfig(sample_rate=SR, frame_ms=30, min_speech_ms=200, hangover_ms=500))
    pending = np.zeros(0, dtype=np.float32)
    segment: list[np.ndarray] = []
    in_seg = False

    async def flush() -> None:
        nonlocal segment
        if not segment:
            return
        audio = np.concatenate(segment)
        segment = []
        if len(audio) < SR * 0.3:
            return
        lang = language if language in ("hi", "en") else None
        try:
            _, res = await st.workers.speech.run("stt_stream", lambda _c: stt.transcribe(audio, language=lang, allow_download=allow_dl), timeout=60)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            await ws.send_text(json.dumps({"type": "error", "code": "stt_failed", "error": str(exc)[:300]}))
            return
        text = (res.text or "").strip()
        if not text:
            return
        from sellagent_ai.sentiment import analyze

        senti = analyze(text).label if speaker == "prospect" else None
        with st.session_factory() as s2:
            seq = (s2.scalar(select(func.max(Transcript.seq)).where(Transcript.call_id == call_id)) or 0) + 1
            s2.add(Transcript(call_id=call_id, seq=seq, speaker=speaker, text=text, language=res.language, confidence=res.language_probability, source="stt", sentiment=senti))
            s2.commit()
        await ws.send_text(json.dumps({"type": "final", "seq": seq, "text": text, "language": res.language, "sentiment": senti, "latency_ms": res.latency_ms}, ensure_ascii=False))

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("text"):
                try:
                    cmd = json.loads(msg["text"])
                except ValueError:
                    continue
                if cmd.get("type") == "stop":
                    await flush()
                    break
                if cmd.get("type") == "speaker" and cmd.get("speaker") in ("prospect", "operator"):
                    await flush()
                    speaker = cmd["speaker"]
                continue
            data = msg.get("bytes")
            if not data:
                continue
            if len(data) % 2:
                data = data[:-1]
            pending = np.concatenate([pending, np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0])
            while len(pending) >= FRAME:
                frame, pending = pending[:FRAME], pending[FRAME:]
                onset = vad.feed(frame)
                if onset:
                    in_seg = True
                    await ws.send_text(json.dumps({"type": "vad", "speech": True}))
                if in_seg:
                    segment.append(frame)
                    if not vad.in_speech or sum(len(x) for x in segment) >= SR * MAX_SEGMENT_S:
                        in_seg = vad.in_speech
                        await flush()
                        if not in_seg:
                            await ws.send_text(json.dumps({"type": "vad", "speech": False}))
            await asyncio.sleep(0)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await ws.close()
        except RuntimeError:
            pass
