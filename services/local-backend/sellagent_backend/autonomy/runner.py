"""Autonomous conversation over a VERIFIED digital call-audio path (spec section 4 loop).

Per turn: conversation state machine (approved facts + guardrails) -> local TTS -> speech written into the call in
100 ms chunks while caller audio is watched for barge-in (remaining speech is cancelled the moment they talk) ->
VAD endpointing on caller audio -> local STT -> language follows the caller -> next turn.

It never runs on an unverified path, and it stops (falling back to the operator) when: emergency stop, opt-out,
the call is no longer live, the path closes, speech recognition is unreliable, the caller is silent, or any model
or audio error occurs. Audio is processed in memory only.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sellagent_ai.conversation import ConversationEngine
from sellagent_speech.audio_io import resample
from sellagent_speech.pipeline import BargeInMonitor
from sellagent_speech.vad import EnergyVAD, VadConfig
from sqlalchemy.orm import Session, sessionmaker

from sellagent_backend.autonomy.path import CallAudioPath
from sellagent_backend.db.models import Call, CallEvent, CallJob
from sellagent_backend.services import call_jobs as svc
from sellagent_backend.services import settings_service
from sellagent_backend.services.conversation import ConversationStepError, run_step

log = logging.getLogger("sellagent.autonomy")
SR = 16000
CHUNK_S = 0.1
LIVE_STATES = {"connected", "greeting", "permission_to_continue", "needs_discovery", "product_explanation", "objection_handling", "demo_invitation", "human_handoff", "followup_scheduling"}
REPEAT = {"en": "Sorry, I didn't catch that. Could you please repeat?", "hi": "माफ़ कीजिए, मैं समझ नहीं पाया। क्या आप दोबारा बोल सकते हैं?"}
BYE_SILENT = {"en": "I could not hear a reply, so I will end the call now. Thank you, goodbye.", "hi": "मुझे जवाब सुनाई नहीं दिया, इसलिए मैं कॉल समाप्त कर रहा हूँ। धन्यवाद, नमस्ते।"}
HANDOFF_POOR_AUDIO = {"en": "The line is not clear, so a FITRON team member will call you back. Thank you.", "hi": "आवाज़ साफ़ नहीं आ रही है, इसलिए FITRON टीम का कोई सदस्य आपको वापस कॉल करेगा। धन्यवाद।"}


@dataclass
class AutonomyConfig:
    max_turns: int = 14
    listen_timeout_s: float = 8.0
    max_utterance_s: float = 15.0
    max_silences: int = 2
    max_unrecognised: int = 2
    speed: float = 1.0


@dataclass
class AutonomousSession:
    call_id: str
    sf: sessionmaker[Session]
    path: CallAudioPath
    engine: ConversationEngine
    stt: Any  # .transcribe(audio_16k, language=..., allow_download=...) -> (.text, .language)
    tts: Any  # .synthesize(text, voice, speed=...) -> (.audio, .sample_rate)
    voices: dict[str, str]
    language: str = "auto"
    config: AutonomyConfig = field(default_factory=AutonomyConfig)
    on_event: Callable[[str, dict[str, Any]], None] = lambda _n, _d: None
    sleep: Callable[[float], None] = time.sleep

    status: str = "starting"  # running | finished | stopped | fallback | error
    outcome: str | None = None
    reason: str | None = None
    turns: int = 0
    interruptions: int = 0
    languages: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    _done: threading.Event = field(default_factory=threading.Event)
    _carry: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))

    # ------------------------------------------------------------------ control
    def request_stop(self, reason: str) -> None:
        if not self._stop.is_set():
            self.reason = reason
            self._stop.set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._done.wait(timeout)

    @property
    def done(self) -> bool:
        return self._done.is_set()

    def to_dict(self) -> dict[str, Any]:
        return {"call_id": self.call_id, "path": self.path.name, "status": self.status, "outcome": self.outcome, "reason": self.reason, "turns": self.turns,
                "interruptions": self.interruptions, "languages": self.languages, "started_at": self.started_at.isoformat(), "finished_at": self.finished_at.isoformat() if self.finished_at else None}

    def _event(self, name: str, **data: Any) -> None:
        try:
            self.on_event(name, {"call_id": self.call_id, **data})
        except Exception:  # noqa: BLE001 - notifications never break the call
            log.exception("autonomy event failed")

    # ------------------------------------------------------------------ safety
    def _blocked(self) -> str | None:
        if self._stop.is_set():
            return self.reason or "stopped"
        if not self.path.is_open():
            return "call audio path closed"
        with self.sf() as s:
            if settings_service.get(s, "calling.emergency_stop_active"):
                return "emergency stop"
            if not settings_service.get(s, "release_gate.autonomous_calling_allowed"):
                return "release gate closed"
            c = s.get(Call, self.call_id)
            if c is None or c.conversation_state not in LIVE_STATES:
                return f"call no longer live ({c.conversation_state if c else 'deleted'})"
        return None

    # ------------------------------------------------------------------ audio
    def speak(self, text: str, lang: str) -> bool:
        """Say ``text`` into the call. Returns False if the caller interrupted (rest of the speech is cancelled)."""
        if not text:
            return True
        voice = self.voices.get(lang) or self.voices.get("en")
        if not voice:
            raise RuntimeError(f"no TTS voice configured for {lang!r}")
        out = self.tts.synthesize(text, voice, speed=self.config.speed)
        audio = resample(np.asarray(out.audio, dtype=np.float32), out.sample_rate, self.path.sample_rate)
        step = int(self.path.sample_rate * CHUNK_S)
        barge = BargeInMonitor(VadConfig(sample_rate=self.path.sample_rate, min_speech_ms=150, hangover_ms=300))
        self._event("autonomy.speaking", text=text, language=lang)
        heard: list[np.ndarray] = []
        for i in range(0, len(audio), step):
            if self._stop.is_set() or not self.path.is_open():
                return False
            self.path.write(audio[i : i + step])
            incoming = self.path.read()
            if len(incoming):
                heard.append(incoming)
                if barge.feed(incoming):
                    self.interruptions += 1
                    self._carry = resample(np.concatenate(heard), self.path.sample_rate, SR)  # keep the start of their words
                    self._event("autonomy.interrupted", spoken_s=round(i / self.path.sample_rate, 2))
                    return False
        return True

    def listen(self) -> np.ndarray | None:
        """VAD endpointing on caller audio. Returns 16 kHz speech or None after the timeout."""
        vad = EnergyVAD(VadConfig(sample_rate=SR, frame_ms=30, min_speech_ms=200, hangover_ms=800))
        frame = vad._frame
        buf, pending = [], self._carry
        self._carry = np.zeros(0, dtype=np.float32)
        started, waited = False, 0.0
        self._event("autonomy.listening")
        while not self._stop.is_set() and self.path.is_open():
            chunk = self.path.read()
            if len(chunk):
                pending = np.concatenate([pending, resample(chunk, self.path.sample_rate, SR)])
            elif not len(pending):
                self.sleep(0.02)
                waited += 0.02
                if not started and waited > self.config.listen_timeout_s:
                    return None
                continue
            while len(pending) >= frame:
                f, pending = pending[:frame], pending[frame:]
                onset = vad.feed(f)
                if started or onset:
                    started = True
                    buf.append(f)
                    if not vad.in_speech or len(buf) * 0.03 >= self.config.max_utterance_s:
                        return np.concatenate(buf)
                else:
                    waited += 0.03
                    if waited > self.config.listen_timeout_s:
                        return None
        return None

    def hear(self, lang: str) -> tuple[str | None, str | None]:
        """Listen + transcribe with bounded retries. Returns (text, detected_language) or (None, reason)."""
        silences = unrecognised = 0
        while True:
            audio = self.listen()
            if self._stop.is_set():
                return None, "stopped"
            if audio is None:
                silences += 1
                if silences >= self.config.max_silences:
                    return None, "silence"
            else:
                res = self.stt.transcribe(audio, language=None, allow_download=False)  # auto-detect: the caller may switch language
                text = (res.text or "").strip()
                if text:
                    self._event("autonomy.heard", text=text, language=res.language)
                    return text, res.language
                unrecognised += 1
                if unrecognised >= self.config.max_unrecognised:
                    return None, "unrecognised"
            self.speak(REPEAT.get(lang, REPEAT["en"]), lang)

    # ------------------------------------------------------------------ main loop
    def run(self) -> None:
        self.status = "running"
        self._event("autonomy.started", path=self.path.name)
        try:
            self._loop()
        except Exception as exc:  # noqa: BLE001 - any failure falls back to the operator
            log.exception("autonomous conversation failed")
            self.status, self.reason = "error", f"{exc.__class__.__name__}: {exc}"[:400]
        finally:
            if self.status == "running":
                self.status = "finished"
            self.finished_at = datetime.now(UTC)
            self._event("autonomy.finished", **self.to_dict())
            self._done.set()

    def _fallback(self, reason: str, *, say: dict[str, str] | None = None, lang: str = "en", outcome: str | None = None) -> None:
        if say and not self._stop.is_set():
            self.speak(say.get(lang, say["en"]), lang)
        self.status, self.reason = ("finished" if outcome else "fallback"), reason
        with self.sf() as s:
            c = s.get(Call, self.call_id)
            if c is not None:
                job = s.get(CallJob, c.call_job_id)
                if outcome and c.outcome is None and job is not None and job.status not in ("completed", "failed", "cancelled"):
                    svc.complete(s, job.id, outcome=outcome, detail=reason, actor="ai_autonomous")
                    if c.conversation_state in LIVE_STATES:
                        c.conversation_state = "completed"
                s.add(CallEvent(call_id=c.id, event_type="autonomy.fallback" if not outcome else "autonomy.ended", from_state=c.conversation_state, to_state=c.conversation_state, source="ai_autonomous", data={"reason": reason, "outcome": outcome}))
                s.commit()
        self.outcome = outcome

    def _loop(self) -> None:
        lang = self.language if self.language in ("hi", "en") else "en"
        utterance: str | None = None
        for _ in range(self.config.max_turns):
            why = self._blocked()
            if why:
                self.status, self.reason = ("stopped" if self._stop.is_set() or why == "emergency stop" else "fallback"), why
                return
            with self.sf() as s:
                c = s.get(Call, self.call_id)
                try:
                    res = run_step(s, c, utterance, engine=self.engine, language=lang, prospect_source="stt", agent_source="ai_autonomous", actor="ai_autonomous")  # type: ignore[arg-type]
                except ConversationStepError as exc:
                    s.rollback()
                    self.status, self.reason = "fallback", f"conversation stopped: {exc}"
                    return
                s.commit()
            self.turns += 1
            lang = res["language"] if res["language"] in ("hi", "en") else lang
            self.languages.append(lang)
            self.speak(res["agent_text"], lang)  # an interruption just moves on to listening
            if res["terminal"]:
                self.status, self.outcome = "finished", res["outcome"]
                return
            text, detected = self.hear(lang)
            if text is None:
                if detected == "stopped":
                    self.status = "stopped"
                    return
                if detected == "silence":
                    self._fallback("prospect stopped replying", say=BYE_SILENT, lang=lang, outcome="callback_requested")
                else:
                    self._fallback("speech recognition unreliable; human follow-up needed", say=HANDOFF_POOR_AUDIO, lang=lang, outcome="human_handoff")
                return
            if detected in ("hi", "en"):
                lang = detected  # follow the caller's language
            utterance = text
        self._fallback(f"turn limit ({self.config.max_turns}) reached", outcome="callback_requested")
