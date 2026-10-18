"""Starts at most one autonomous conversation at a time, only when every gate holds:

release gate open (real-device digital audio evidence) + calling.autonomous_enabled + emergency stop clear +
live transcription allowed + live call + contact consent granted and not opted out + the call's telecom adapter
provides a VERIFIED digital call-audio path. Nothing here dials; calls are placed by the normal call-job flow.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from sellagent_backend.autonomy.path import CallAudioPath, NoVerifiedPath
from sellagent_backend.autonomy.runner import LIVE_STATES, AutonomousSession, AutonomyConfig
from sellagent_backend.db.models import Call, Contact
from sellagent_backend.services import settings_service

log = logging.getLogger("sellagent.autonomy")
Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
Components = Callable[[Session], tuple[Any, Any, dict[str, str]]]  # -> (stt, tts, voices)


class AutonomyError(RuntimeError):
    def __init__(self, msg: str, code: str) -> None:
        super().__init__(msg)
        self.code = code


def default_components(app_settings: Any) -> Components:
    def build(s: Session) -> tuple[Any, Any, dict[str, str]]:
        from sellagent_speech import FasterWhisperSTT, PiperTTS

        stt = FasterWhisperSTT(settings_service.get(s, "ai.whisper_model"), models_dir=app_settings.models_dir)
        ok, msg = stt.available()
        if not ok:
            raise AutonomyError(msg, "stt_unavailable")
        tts = PiperTTS(app_settings.models_dir, executable=settings_service.get(s, "ai.piper_executable") or None)
        ok, msg = tts.available()
        if not ok:
            raise AutonomyError(msg, "tts_unavailable")
        return stt, tts, {"en": settings_service.get(s, "ai.piper_voice_en"), "hi": settings_service.get(s, "ai.piper_voice_hi")}

    return build


class AutonomyManager:
    def __init__(self, sf: sessionmaker[Session], engine_factory: Callable[..., Any], emit: Emit, components: Components) -> None:
        self.sf = sf
        self.engine_factory = engine_factory
        self.emit = emit
        self.components = components
        self.loop: asyncio.AbstractEventLoop | None = None
        self.active: AutonomousSession | None = None
        self.history: list[dict[str, Any]] = []
        self.sleep: Callable[[float], None] = time.sleep  # tests replace this to run silence windows instantly
        self._lock = threading.Lock()

    def _emit_sync(self, name: str, data: dict[str, Any]) -> None:
        loop = self.loop
        if loop is not None and not loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(self.emit(name, data), loop)
            except RuntimeError:
                pass

    def preflight(self, s: Session, call_id: str, path: CallAudioPath | None) -> Call:
        if settings_service.get(s, "calling.emergency_stop_active"):
            raise AutonomyError("emergency stop is active", "emergency_stop")
        if not settings_service.get(s, "release_gate.autonomous_calling_allowed"):
            raise AutonomyError("autonomous calling is locked: no real-device evidence of two-way DIGITAL call audio (see Devices > Audio feasibility)", "release_gate_closed")
        if not settings_service.get(s, "calling.autonomous_enabled"):
            raise AutonomyError("autonomous calling is switched off (Settings: calling.autonomous_enabled)", "autonomous_disabled")
        if not settings_service.get(s, "privacy.allow_live_transcription"):
            raise AutonomyError("autonomous calls need live transcription (Settings: privacy.allow_live_transcription)", "transcription_disabled")
        c = s.get(Call, call_id)
        if c is None:
            raise AutonomyError("call not found", "not_found")
        if c.conversation_state not in LIVE_STATES:
            raise AutonomyError(f"call is not live ({c.conversation_state})", "not_live")
        contact = s.get(Contact, c.contact_id)
        if contact is None or contact.opted_out:
            raise AutonomyError("contact opted out", "contact_not_allowed")
        if contact.consent_status != "granted":
            raise AutonomyError(f"contact consent is {contact.consent_status!r}", "contact_not_allowed")
        if path is None:
            raise NoVerifiedPath("this call's route has no verified digital call-audio path (the Android/Jio route offers none; see docs/FEASIBILITY_REPORT.md)")
        return c

    def start(self, call_id: str, path: CallAudioPath | None, *, language: str = "auto", use_llm: bool = True) -> AutonomousSession:
        with self._lock:
            if self.active is not None and not self.active.done:
                raise AutonomyError("an autonomous conversation is already running; one call at a time", "busy")
            with self.sf() as s:
                try:
                    self.preflight(s, call_id, path)
                except NoVerifiedPath as exc:
                    raise AutonomyError(str(exc), "no_verified_audio_path") from exc
                stt, tts, voices = self.components(s)
                speed = max(50, min(200, int(settings_service.get(s, "ai.tts_speed_percent")))) / 100
                cfg = AutonomyConfig(speed=speed)
            assert path is not None
            session = AutonomousSession(call_id=call_id, sf=self.sf, path=path, engine=self.engine_factory(use_llm=use_llm), stt=stt, tts=tts, voices=voices, language=language, config=cfg, on_event=self._emit_sync, sleep=self.sleep)
            self.active = session
        threading.Thread(target=self._run, args=(session,), name=f"autonomy-{call_id[:8]}", daemon=True).start()
        return session

    def _run(self, session: AutonomousSession) -> None:
        try:
            session.run()
        finally:
            try:
                session.path.close()
            except Exception:  # noqa: BLE001
                log.exception("closing call audio path failed")
            self.history = ([session.to_dict()] + self.history)[:20]

    def stop(self, reason: str = "operator took over") -> bool:
        a = self.active
        if a is None or a.done:
            return False
        a.request_stop(reason)
        return True

    def emergency_stop(self) -> None:
        self.stop("emergency stop")

    def status(self) -> dict[str, Any]:
        a = self.active
        return {"active": a.to_dict() if a and not a.done else None, "last": a.to_dict() if a and a.done else None, "history": self.history}
