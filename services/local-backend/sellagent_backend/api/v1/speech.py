"""Local speech diagnostics on the PC (labelled simulated/local). Not cellular audio."""

from __future__ import annotations

import asyncio
import base64
import io
import wave

import numpy as np
from fastapi import APIRouter, Depends, File, Request, UploadFile
from sellagent_speech import FasterWhisperSTT, PiperTTS, STTUnavailable, TTSUnavailable
from sellagent_speech.audio_io import devices, resample
from sellagent_speech.diagnostics import synthetic_vad_selftest, tts_to_stt_loopback
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_area
from sellagent_backend.api.schemas import TTSIn
from sellagent_backend.api.v1.errors import bad_request
from sellagent_backend.db.models import AIRun
from sellagent_backend.services import settings_service

router = APIRouter(prefix="/speech", tags=["speech"], dependencies=[Depends(require_area("speech"))])


@router.get("/status")
def status(request: Request, db: Session = Depends(get_db)) -> dict:
    s = request.app.state.settings
    stt = FasterWhisperSTT(settings_service.get(db, "ai.whisper_model"), models_dir=s.models_dir)
    tts = PiperTTS(s.models_dir, executable=settings_service.get(db, "ai.piper_executable") or None)
    stt_ok, stt_msg = stt.available()
    tts_ok, tts_msg = tts.available()
    return {"stt": {"engine": "faster-whisper", "available": stt_ok, "message": stt_msg, "model": stt.model_size}, "tts": {"engine": "piper", "available": tts_ok, "message": tts_msg, "voices": tts.list_voices(), "voice_en": settings_service.get(db, "ai.piper_voice_en"), "voice_hi": settings_service.get(db, "ai.piper_voice_hi")}, "vad": synthetic_vad_selftest(), "audio_devices": devices(), "models_dir": str(s.models_dir), "label": "PC-local diagnostics; says nothing about phone call audio"}


def _wav_bytes(audio: np.ndarray, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


@router.post("/tts")
async def tts(body: TTSIn, request: Request, db: Session = Depends(get_db)) -> dict:
    s = request.app.state.settings
    from sellagent_backend.services import persona_service

    voice = persona_service.voices(db)["hi" if body.language == "hi" else "en"]
    opts = persona_service.tts_options(db)
    if not voice:
        raise bad_request(f"no Piper voice configured for {body.language}; see models/README.md", code="no_voice")
    try:
        res = await asyncio.to_thread(PiperTTS(s.models_dir, executable=settings_service.get(db, "ai.piper_executable") or None).synthesize, body.text, voice, opts["speed"], volume=opts["volume"], pause_ms=opts["pause_ms"])
    except TTSUnavailable as exc:
        raise bad_request(str(exc), code="tts_unavailable") from exc
    db.add(AIRun(kind="tts", provider="piper", model=voice, prompt_chars=len(body.text), total_ms=res.latency_ms, success=True, offline=True))
    return {"voice": voice, "sample_rate": res.sample_rate, "latency_ms": res.latency_ms, "duration_s": len(res.audio) / res.sample_rate, "wav_base64": base64.b64encode(_wav_bytes(res.audio, res.sample_rate)).decode()}


@router.post("/stt")
async def stt(request: Request, db: Session = Depends(get_db), file: UploadFile = File(...), language: str | None = None) -> dict:
    s = request.app.state.settings
    data = await file.read()
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            rate, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
            frames = w.readframes(w.getnframes())
    except wave.Error as exc:
        raise bad_request(f"upload a 16-bit PCM WAV file: {exc}") from exc
    if sw != 2:
        raise bad_request("WAV must be 16-bit PCM")
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    audio = resample(audio, rate, 16000)
    allow = bool(s.allow_external_network) or bool(settings_service.get(db, "privacy.allow_external_network"))
    engine = FasterWhisperSTT(settings_service.get(db, "ai.whisper_model"), models_dir=s.models_dir)
    try:
        res = await asyncio.to_thread(engine.transcribe, audio, language=language if language in ("hi", "en") else None, allow_download=allow)
    except STTUnavailable as exc:
        raise bad_request(str(exc), code="stt_unavailable") from exc
    db.add(AIRun(kind="stt", provider="faster-whisper", model=res.model, total_ms=res.latency_ms, output_chars=len(res.text), success=True, offline=not allow))
    return {"text": res.text, "language": res.language, "language_probability": res.language_probability, "audio_duration_s": res.duration_s, "latency_ms": res.latency_ms, "model_load_ms": engine.load_ms, "segments": res.segments}


@router.post("/pipeline-test")
async def pipeline_test(request: Request, db: Session = Depends(get_db), file: UploadFile = File(...), language: str | None = None, use_llm: bool = False) -> dict:
    """PRERECORDED-AUDIO pipeline test: WAV -> VAD -> faster-whisper -> conversation engine (approved facts +
    guardrails) -> Piper. Measures every stage. Proves the local AI voice pipeline only; NOT call audio."""
    from sellagent_ai.conversation import ConversationContext, ConversationStateMachine, State
    from sellagent_speech.pipeline import VoicePipeline
    from sellagent_speech.vad import make_vad

    from sellagent_backend.services.conversation import facts_for

    s = request.app.state.settings
    audio = _read_wav_16k(await file.read())
    allow = bool(s.allow_external_network) or bool(settings_service.get(db, "privacy.allow_external_network"))
    stt_engine = FasterWhisperSTT(settings_service.get(db, "ai.whisper_model"), models_dir=s.models_dir)
    ok, msg = stt_engine.available()
    if not ok:
        raise bad_request(msg, code="stt_unavailable")
    tts = PiperTTS(s.models_dir, executable=settings_service.get(db, "ai.piper_executable") or None)
    from sellagent_backend.services import persona_service

    voices = persona_service.voices(db)
    engine = request.app.state.conversation_engine(use_llm=use_llm)

    def respond(text: str, lang: str | None) -> tuple[str, str]:
        with request.app.state.session_factory() as s2:
            facts = facts_for(s2, text)
            persona = persona_service.load_persona(s2)
        sm = ConversationStateMachine(State.PRODUCT_EXPLANATION)
        turn = engine.respond(sm, text, facts=facts, ctx=ConversationContext(authorized=True), preferred_language=language or lang or "auto", persona=persona)
        return turn.agent_text, turn.language

    try:
        vad = make_vad(settings_service.get(db, "ai.vad_engine"))
    except RuntimeError as exc:
        raise bad_request(str(exc), code="vad_unavailable") from exc
    pipe = VoicePipeline(vad=vad, stt=stt_engine, tts=tts if tts.available()[0] else None, respond=respond, voices=voices, allow_download=allow)
    _, turn = await request.app.state.workers.speech.run("pipeline_test", lambda _c: pipe.run(audio, language=language if language in ("hi", "en") else None), timeout=180)
    db.add(AIRun(kind="benchmark", provider="pipeline:" + turn.vad_engine + "+faster-whisper+piper", model=settings_service.get(db, "ai.whisper_model"), total_ms=turn.timings_ms.get("total"), success=turn.status in ("ok", "no_speech"), error=turn.error, offline=not allow))
    out = {"label": "PRERECORDED_AUDIO_PIPELINE (not call audio)", **turn.to_dict()}
    if turn.reply_audio is not None and turn.reply_sample_rate:
        out["reply_wav_base64"] = base64.b64encode(_wav_bytes(turn.reply_audio, turn.reply_sample_rate)).decode()
    return out


def _read_wav_16k(data: bytes) -> np.ndarray:
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            rate, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError) as exc:
        raise bad_request(f"upload a 16-bit PCM WAV file: {exc}", code="bad_audio") from exc
    if sw != 2:
        raise bad_request("WAV must be 16-bit PCM", code="bad_audio")
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    return resample(audio, rate, 16000)


@router.post("/loopback")
async def loopback(request: Request, db: Session = Depends(get_db), language: str = "en") -> dict:
    """SIMULATED loopback: Piper -> VAD -> Whisper on the PC. Proves the local pipeline, not call audio."""
    if language not in ("hi", "en"):
        raise bad_request("language must be hi or en")
    s = request.app.state.settings
    voice = settings_service.get(db, "ai.piper_voice_hi" if language == "hi" else "ai.piper_voice_en") or None
    results = await asyncio.to_thread(tts_to_stt_loopback, s.models_dir, language=language, voice=voice, whisper_model=settings_service.get(db, "ai.whisper_model"))
    for r in results:
        db.add(AIRun(kind="benchmark", provider="piper+faster-whisper", model=f"{voice}|{settings_service.get(db, 'ai.whisper_model')}", total_ms=(r.tts_latency_ms or 0) + (r.stt_latency_ms or 0), success=r.error is None, error=r.error, offline=True))
    return {"label": "SIMULATED_LOOPBACK", "language": language, "results": [r.to_dict() for r in results]}
