"""Runs at most one acoustic AI bridge at a time, always started by the operator on a call they are watching.

The bridge does not open the autonomous-calling release gate and nothing here dials on its own."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from sellagent_backend.bridge.audio import DeviceChoice, Listener, MicListener, PiperSpeaker, Speaker
from sellagent_backend.bridge.session import (
    LIVE_STATES,
    BridgeConfig,
    BridgeError,
    BridgeSession,
    contact_ok_for_bridge,
)
from sellagent_backend.db.models import Call
from sellagent_backend.services import settings_service

log = logging.getLogger("sellagent.bridge")
Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
AudioFactory = Callable[[Session], tuple[Speaker, Listener]]


def default_audio_factory(app_settings: Any, stt_cache: dict[str, Any]) -> AudioFactory:
    """Real PC audio: Piper voices + faster-whisper, devices from settings."""

    def build(s: Session) -> tuple[Speaker, Listener]:
        from sellagent_speech import FasterWhisperSTT, PiperTTS

        model = settings_service.get(s, "ai.whisper_model")
        stt = stt_cache.get(model)
        if stt is None:
            stt = stt_cache[model] = FasterWhisperSTT(model, models_dir=app_settings.models_dir)
        ok, msg = stt.available()
        if not ok:
            raise BridgeError(msg, "stt_unavailable")
        tts = PiperTTS(app_settings.models_dir)
        ok, msg = tts.available()
        if not ok:
            raise BridgeError(msg, "tts_unavailable")
        devices = DeviceChoice(settings_service.get(s, "bridge.input_device") or None, settings_service.get(s, "bridge.output_device") or None)
        voices = {"en": settings_service.get(s, "ai.piper_voice_en"), "hi": settings_service.get(s, "ai.piper_voice_hi")}
        allow = bool(app_settings.allow_external_network) or bool(settings_service.get(s, "privacy.allow_external_network"))
        return PiperSpeaker(tts, voices, devices), MicListener(stt, allow_download=allow, devices=devices, energy_threshold_db=-abs(float(settings_service.get(s, "bridge.mic_threshold_db"))))

    return build


def _stop_pc_audio() -> None:
    try:
        import sounddevice as sd

        sd.stop()
    except Exception:  # noqa: BLE001 - nothing playing / no PortAudio
        log.debug("sounddevice.stop() failed", exc_info=True)


class BridgeManager:
    def __init__(self, sf: sessionmaker[Session], engine_factory: Callable[..., Any], emit: Emit, audio_factory: AudioFactory, *, stop_audio: Callable[[], None] = _stop_pc_audio) -> None:
        self.sf = sf
        self.engine_factory = engine_factory
        self.emit = emit
        self.audio_factory = audio_factory
        self.stop_audio = stop_audio
        self.loop: asyncio.AbstractEventLoop | None = None
        self.active: BridgeSession | None = None
        self.history: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ events
    def _emit_sync(self, name: str, data: dict[str, Any]) -> None:
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.emit(name, data), loop)
        except RuntimeError:
            pass

    # ------------------------------------------------------------------ checks
    def preflight(self, s: Session, call_id: str) -> Call:
        if not settings_service.get(s, "bridge.enabled"):
            raise BridgeError("the AI voice bridge is switched off (Settings: bridge.enabled)", "bridge_disabled")
        if settings_service.get(s, "calling.emergency_stop_active"):
            raise BridgeError("emergency stop is active", "emergency_stop")
        if not settings_service.get(s, "privacy.allow_live_transcription"):
            raise BridgeError("the AI needs live transcription; enable Settings: privacy.allow_live_transcription", "transcription_disabled")
        c = s.get(Call, call_id)
        if c is None:
            raise BridgeError("call not found", "not_found")
        if c.conversation_state not in LIVE_STATES:
            raise BridgeError(f"call is not live ({c.conversation_state}); mark it Connected first", "not_live")
        reason = contact_ok_for_bridge(s, c)
        if reason:
            raise BridgeError(reason, "contact_not_allowed")
        return c

    # ------------------------------------------------------------------ control
    def start(self, call_id: str, *, language: str = "auto", use_llm: bool = True, supervised: bool = True) -> BridgeSession:
        with self._lock:
            if self.active is not None and not self.active.done:
                raise BridgeError(f"the AI is already on call {self.active.call_id[:8]}; one call at a time", "busy")
            with self.sf() as s:
                self.preflight(s, call_id)
                speaker, listener = self.audio_factory(s)
                cfg = BridgeConfig(
                    max_turns=int(settings_service.get(s, "bridge.max_turns")), listen_timeout_s=float(settings_service.get(s, "bridge.listen_timeout_s")),
                    max_utterance_s=float(settings_service.get(s, "bridge.max_utterance_s")), max_silences=int(settings_service.get(s, "bridge.max_silences")),
                )
            session = BridgeSession(
                call_id=call_id, sf=self.sf, engine=self.engine_factory(use_llm=use_llm), speaker=speaker, listener=listener, language=language,
                supervised=supervised, config=cfg, on_event=self._emit_sync, stop_audio=self.stop_audio,
            )
            self.active = session
        t = threading.Thread(target=self._run, args=(session,), name=f"ai-bridge-{call_id[:8]}", daemon=True)
        t.start()
        return session

    def _run(self, session: BridgeSession) -> None:
        session.run()
        self.history = ([session.to_dict()] + self.history)[:20]

    def stop(self, reason: str = "operator took over") -> bool:
        s = self.active
        if s is None or s.done:
            return False
        s.request_stop(reason)
        return True

    def emergency_stop(self) -> None:
        self.stop("emergency stop")

    def status(self) -> dict[str, Any]:
        a = self.active
        return {"active": a.to_dict() if a and not a.done else None, "last": a.to_dict() if a and a.done else None, "history": self.history}

