"""Acoustic AI bridge: runs one live call's conversation through the PC speaker and microphone.

Flow per call:
1. Ask for consent to talk with an automated assistant that converts speech to text (spoken notice).
2. Only after a clear "yes": record transcription consent, then run the normal conversation engine turn by
   turn (same state machine, approved knowledge and guardrails as the operator console).
3. Opt-out, "talk to a person", silence, emergency stop or operator take-over end the AI part immediately.

Safety facts (consent, opt-out, emergency stop, suppression) come from the database at every turn, never from the
model. Audio is processed in memory only.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sellagent_ai.conversation import ConversationEngine
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sellagent_backend.bridge.audio import Listener, Speaker
from sellagent_backend.db.models import AudioTest, Call, CallEvent, CallJob, Contact, PairedDevice, Transcript
from sellagent_backend.services import audit, settings_service
from sellagent_backend.services import call_jobs as svc
from sellagent_backend.services.conversation import ConversationStepError, next_seq, run_step

log = logging.getLogger("sellagent.bridge")

LIVE_STATES = {"connected", "greeting", "permission_to_continue", "needs_discovery", "product_explanation", "objection_handling", "demo_invitation", "human_handoff", "followup_scheduling"}
BRIDGE_STEP = "acoustic_bridge_call"

CONSENT_PROMPT = {
    "en": "Namaste. This is an automated AI assistant calling for FITRON. To talk with you, it converts your words into text; nothing is recorded. Is that okay? Please say yes or no.",
    "hi": "नमस्ते। मैं FITRON की ओर से एक स्वचालित AI सहायक हूँ। आपसे बात करने के लिए मैं आपकी बातों को टेक्स्ट में बदलता हूँ; कोई रिकॉर्डिंग नहीं होती। क्या यह ठीक है? कृपया हाँ या नहीं कहें।",
}
REPEAT = {"en": "Sorry, I could not hear you. Is it okay to continue? Please say yes or no.", "hi": "माफ़ कीजिए, मैं सुन नहीं पाया। क्या बात आगे बढ़ाएँ? कृपया हाँ या नहीं कहें।"}
ARE_YOU_THERE = {"en": "Sorry, I didn't catch that. Could you please repeat?", "hi": "माफ़ कीजिए, मैं समझ नहीं पाया। क्या आप दोबारा बोल सकते हैं?"}
NO_REPLY_BYE = {"en": "I could not hear a reply, so I will end the call now. Thank you, goodbye.", "hi": "मुझे जवाब सुनाई नहीं दिया, इसलिए मैं कॉल समाप्त कर रहा हूँ। धन्यवाद, नमस्ते।"}
NO_CONSENT_BYE = {"en": "No problem. Thank you for your time. Goodbye.", "hi": "कोई बात नहीं। आपके समय के लिए धन्यवाद। नमस्ते।"}
HANDOFF = {"en": "Sure. A FITRON team member will call you back. Thank you, goodbye.", "hi": "ज़रूर। FITRON टीम का कोई सदस्य आपको वापस कॉल करेगा। धन्यवाद, नमस्ते।"}


class BridgeError(RuntimeError):
    def __init__(self, msg: str, code: str = "bridge_error") -> None:
        super().__init__(msg)
        self.code = code


@dataclass
class BridgeConfig:
    max_turns: int = 14
    listen_timeout_s: float = 8.0
    max_utterance_s: float = 15.0
    max_silences: int = 2


@dataclass
class BridgeSession:
    call_id: str
    sf: sessionmaker[Session]
    engine: ConversationEngine
    speaker: Speaker
    listener: Listener
    language: str = "auto"
    supervised: bool = True
    config: BridgeConfig = field(default_factory=BridgeConfig)
    on_event: Callable[[str, dict[str, Any]], None] = lambda _n, _d: None
    stop_audio: Callable[[], None] = lambda: None

    status: str = "starting"  # starting | running | finished | stopped | error
    outcome: str | None = None
    error: str | None = None
    stop_reason: str | None = None
    agent_lines: int = 0
    prospect_utterances: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    _done: threading.Event = field(default_factory=threading.Event)

    # ------------------------------------------------------------------ control
    def request_stop(self, reason: str) -> None:
        if not self._stop.is_set():
            self.stop_reason = reason
            self._stop.set()
            self.stop_audio()

    def wait(self, timeout: float | None = None) -> bool:
        return self._done.wait(timeout)

    @property
    def done(self) -> bool:
        return self._done.is_set()

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id, "status": self.status, "outcome": self.outcome, "error": self.error, "stop_reason": self.stop_reason,
            "supervised": self.supervised, "agent_lines": self.agent_lines, "prospect_utterances": self.prospect_utterances,
            "started_at": self.started_at.isoformat(), "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }

    # ------------------------------------------------------------------ helpers
    def _stopping(self) -> bool:
        if self._stop.is_set():
            return True
        with self.sf() as s:
            if settings_service.get(s, "calling.emergency_stop_active"):
                self.request_stop("emergency stop")
                return True
            c = s.get(Call, self.call_id)
            if c is None or c.conversation_state not in LIVE_STATES:
                self.request_stop(f"call no longer live ({c.conversation_state if c else 'deleted'})")
                return True
        return False

    def _event(self, name: str, **data: Any) -> None:
        try:
            self.on_event(name, {"call_id": self.call_id, **data})
        except Exception:  # noqa: BLE001 - UI notification must never break the call
            log.exception("bridge event %s failed", name)

    def _say(self, text: str, lang: str, *, store: bool = False) -> None:
        if not text or self._stop.is_set():
            return
        self._event("bridge.speaking", text=text, language=lang)
        if store:
            with self.sf() as s:
                s.add(Transcript(call_id=self.call_id, seq=next_seq(s, self.call_id), speaker="agent", text=text, language=lang, source="bridge"))
                s.commit()
        self.speaker.speak(text, lang)
        self.agent_lines += 1

    def _hear(self, lang: str) -> str | None:
        if self._stop.is_set():
            return None
        self._event("bridge.listening", language=lang)
        text = self.listener.listen(timeout_s=self.config.listen_timeout_s, max_utterance_s=self.config.max_utterance_s, language=lang if lang in ("hi", "en") else None, should_stop=self._stop.is_set)
        if text:
            self.prospect_utterances += 1
            self._event("bridge.heard", text=text)
        return text

    def _hear_with_retry(self, lang: str, retry_text: dict[str, str]) -> str | None:
        for attempt in range(max(1, self.config.max_silences)):
            text = self._hear(lang)
            if text or self._stopping():
                return text
            if attempt + 1 < self.config.max_silences:
                self._say(retry_text.get(lang, retry_text["en"]), lang)
        return None

    def _complete(self, outcome: str, detail: str) -> None:
        with self.sf() as s:
            c = s.get(Call, self.call_id)
            if c is None:
                return
            job = s.get(CallJob, c.call_job_id)
            if c.outcome is None and job is not None and job.status not in ("completed", "failed", "cancelled"):
                svc.complete(s, job.id, outcome=outcome, detail=detail, actor="ai_bridge")
            if c.conversation_state in LIVE_STATES:
                c.conversation_state = "completed"
            s.add(CallEvent(call_id=c.id, event_type="bridge.finished", from_state=c.conversation_state, to_state=c.conversation_state, source="bridge", data={"outcome": outcome, "detail": detail}))
            s.commit()
        self.outcome = outcome

    def _lang(self) -> str:
        if self.language in ("hi", "en"):
            return self.language
        with self.sf() as s:
            pref = settings_service.get(s, "ai.language")
        return pref if pref in ("hi", "en") else "en"

    # ------------------------------------------------------------------ main
    def run(self) -> None:
        self.status = "running"
        self._event("bridge.started", supervised=self.supervised)
        try:
            self._run()
            if self._stop.is_set() and self.outcome is None:
                self.status = "stopped"
            else:
                self.status = "finished"
        except Exception as exc:  # noqa: BLE001 - audio/model failures end the AI part, never crash the backend
            log.exception("bridge failed")
            self.status, self.error = "error", f"{exc.__class__.__name__}: {exc}"[:400]
        finally:
            self.finished_at = datetime.now(UTC)
            if self.supervised:
                self._record_evidence()
            self._event("bridge.finished", **self.to_dict())
            self._done.set()

    def _run(self) -> None:
        lang = self._lang()
        if self._stopping():
            return
        # 1. spoken notice + consent
        self._say(CONSENT_PROMPT[lang], lang, store=True)
        reply = self._hear_with_retry(lang, REPEAT)
        if self._stop.is_set():
            return
        if reply is None:
            self._say(NO_REPLY_BYE[lang], lang)
            self._complete("no_answer", "no reply to the AI consent question")
            return
        intent = ConversationEngine.classify_intent(reply)
        if intent == "opt_out":
            with self.sf() as s:
                c = s.get(Call, self.call_id)
                res = run_step(s, c, reply, engine=self.engine, language=lang, prospect_source="stt", agent_source="bridge", actor="ai_bridge")  # type: ignore[arg-type]
                s.commit()
            self._say(res["agent_text"], res["language"])
            self.outcome = "opted_out"
            return
        if intent == "human":
            self._say(HANDOFF[lang], lang)
            self._complete("human_handoff", "asked for a person at the AI consent question")
            return
        if intent != "affirm":
            self._say(NO_CONSENT_BYE[lang], lang)
            self._complete("not_interested", f"did not agree to the AI assistant: {reply[:120]!r}")
            return
        with self.sf() as s:
            c = s.get(Call, self.call_id)
            assert c is not None
            c.transcription_consent_at = datetime.now(UTC)
            s.add(Transcript(call_id=c.id, seq=next_seq(s, c.id), speaker="prospect", text=reply, language=lang, source="stt"))
            audit.record(s, "call.transcription_consent", actor="ai_bridge", entity_type="call", entity_id=c.id, severity="warning", data={"via": "ai_bridge_spoken_consent", "prompt": CONSENT_PROMPT[lang], "reply": reply[:200]})
            s.commit()

        # 2. conversation turns
        utterance: str | None = None
        for _ in range(self.config.max_turns):
            if self._stopping():
                return
            with self.sf() as s:
                c = s.get(Call, self.call_id)
                try:
                    res = run_step(s, c, utterance, engine=self.engine, language=lang, prospect_source="stt", agent_source="bridge", actor="ai_bridge")  # type: ignore[arg-type]
                except ConversationStepError as exc:
                    s.rollback()
                    self.request_stop(f"conversation ended: {exc}")
                    return
                s.commit()
            lang = res["language"] if res["language"] in ("hi", "en") else lang
            self._say(res["agent_text"], lang)
            if res["terminal"]:
                self.outcome = res["outcome"]
                return
            utterance = self._hear_with_retry(lang, ARE_YOU_THERE)
            if self._stop.is_set():
                return
            if utterance is None:
                self._say(NO_REPLY_BYE[lang], lang)
                self._complete("callback_requested", "prospect stopped replying during the AI call")
                return
        self._say(NO_CONSENT_BYE[lang], lang)
        self._complete("callback_requested", f"AI turn limit ({self.config.max_turns}) reached")

    def _record_evidence(self) -> None:
        """A supervised bridge call becomes a pending audio-test row the operator confirms after listening."""
        try:
            with self.sf() as s:
                c = s.get(Call, self.call_id)
                job = s.get(CallJob, c.call_job_id) if c else None
                dev = s.get(PairedDevice, job.device_id) if job and job.device_id else None
                n_prospect = len(list(s.scalars(select(Transcript.id).where(Transcript.call_id == self.call_id, Transcript.speaker == "prospect", Transcript.source == "stt"))))
                passed = self.error is None and self.prospect_utterances >= 2 and self.agent_lines >= 2
                s.add(AudioTest(
                    test_id=f"BRIDGE-{self.started_at:%Y%m%d-%H%M}", device_id=dev.id if dev else None, step=BRIDGE_STEP, direction="both",
                    status="pass" if passed else "fail", kind="real_device", api_used="PC speaker + PC microphone acoustic bridge (Piper TTS, faster-whisper STT)",
                    phone_model=dev.model if dev else None, android_version=dev.android_version if dev else None, network_config=None,
                    expected="The prospect hears the AI clearly and the AI transcribes the prospect's replies.",
                    actual=f"{self.agent_lines} AI lines spoken, {self.prospect_utterances} prospect replies transcribed; status {self.status}; outcome {self.outcome}",
                    error_message=self.error or self.stop_reason,
                    metrics={"agent_lines": self.agent_lines, "prospect_utterances": self.prospect_utterances, "duration_s": (time.time() - self.started_at.timestamp())},
                    evidence={"call_id": self.call_id, "prospect_utterances": self.prospect_utterances, "agent_lines": self.agent_lines, "stored_prospect_lines": n_prospect},
                ))
                s.commit()
        except Exception:  # noqa: BLE001
            log.exception("could not record bridge evidence")


def contact_ok_for_bridge(s: Session, c: Call) -> str | None:
    """Return a reason the AI may not talk on this call, or None."""
    contact = s.get(Contact, c.contact_id)
    if contact is None:
        return "contact not found"
    if contact.opted_out:
        return "contact opted out"
    if settings_service.get(s, "calling.require_consent") and contact.consent_status != "granted":
        return f"contact consent is {contact.consent_status!r}; the AI only calls contacts who agreed to be called"
    return None

