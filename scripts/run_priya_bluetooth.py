#!/usr/bin/env python3
"""Run Priya (the SELL AGENT female AI) over the Bluetooth hands-free call audio on this PC.

This is the PC-side runner for the verified Bluetooth path (docs/BLUETOOTH_AUDIO.md): it captures the caller from
the phone's "Hands-Free HF Audio" INPUT device, runs the fully local loop (faster-whisper STT -> FITRON
conversation engine with the approved facts + guardrails + the female persona -> Piper TTS), and plays Priya's
voice back to the phone's "Hands-Free HF Audio" OUTPUT device, so the remote party hears her. All local, no cloud.

SAFETY — read this:
  * This is a SUPERVISED test tool for ONE consenting participant, not a bulk auto-dialer. You must pass
    --consent to run a real call, confirming the other party agreed to talk to an AI.
  * Priya always discloses she is an AI, speaks only approved FITRON facts, and honours opt-out ("do not call
    me") immediately. Press Ctrl-C at any time for an emergency stop (she stops talking and the call is ended).
  * Promotional autonomous calling of lists stays OUT of scope here and requires India DLT/consent compliance
    (docs/COMPLIANCE_INDIA.md). Do not use this to cold-call strangers.

Quick start (after models are installed, see docs/BLUETOOTH_AUDIO.md):
    python scripts/run_priya_bluetooth.py --selftest          # no phone/models: proves the wiring
    python scripts/run_priya_bluetooth.py --list-devices      # show audio devices, pick the HF ones
    python scripts/run_priya_bluetooth.py --consent --contact "Rahul" --business "Power Gym"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in ("services/local-backend", "services/ai-engine", "services/speech-engine", "services/knowledge-base", "packages/shared-protocol"):
    sys.path.insert(0, str(_ROOT / _p))

import numpy as np  # noqa: E402
from sellagent_ai.conversation import (  # noqa: E402
    ConversationContext,
    ConversationEngine,
    ConversationStateMachine,
    KnowledgeFact,
    State,
)
from sellagent_ai.conversation import scripts as cscripts  # noqa: E402
from sellagent_ai.persona import ConversationMemory, Persona  # noqa: E402

SR = 16_000
CHUNK_S = 0.1
LIVE = {State.CONNECTED, State.GREETING, State.PERMISSION_TO_CONTINUE, State.NEEDS_DISCOVERY, State.PRODUCT_EXPLANATION, State.OBJECTION_HANDLING, State.DEMO_INVITATION, State.FOLLOWUP_SCHEDULING}
REPEAT = {"en": "Sorry, I didn't catch that. Could you please repeat?", "hi": "माफ़ कीजिए, मैं समझ नहीं पाई। क्या आप दोबारा बोल सकते हैं?"}


def approved_fitron_facts() -> list[KnowledgeFact]:
    """Only APPROVED seed facts (the unapproved first-100 offer is excluded until configured/approved)."""
    from sellagent_kb.service import FITRON_SEED

    out = []
    for i, e in enumerate(FITRON_SEED):
        if e.get("approved", False):
            out.append(KnowledgeFact(f"kb:seed{i}#v1", e["title"], e["category"], e["body"], e.get("structured")))
    return out


# --------------------------------------------------------------------------- phone control (ADB, no root)
class Phone:
    def __init__(self, adb: str = "adb") -> None:
        self.adb = adb

    def _run(self, *args: str) -> str:
        import subprocess

        return subprocess.run([self.adb, "shell", *args], capture_output=True, text=True, timeout=15).stdout  # noqa: S603

    def call_state(self) -> str:
        import re

        m = re.search(r"mCallState\s*=\s*(\d)", self._run("dumpsys", "telephony.registry"))
        return {"0": "IDLE", "1": "RINGING", "2": "IN_CALL"}.get(m.group(1) if m else "", "unknown")

    def dial(self, number: str) -> None:
        self._run("am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{number}")

    def hang_up(self) -> None:
        self._run("telecom", "end-call")


# --------------------------------------------------------------------------- audio devices
def find_hf_devices(match: str = "HF Audio"):  # type: ignore[no-untyped-def]
    """Return (in_index, out_index, samplerate) for the phone's Hands-Free call channel, or raise."""
    import sounddevice as sd

    devs = sd.query_devices()
    ins = [i for i, d in enumerate(devs) if match.lower() in d["name"].lower() and d["max_input_channels"] > 0]
    outs = [i for i, d in enumerate(devs) if match.lower() in d["name"].lower() and d["max_output_channels"] > 0]
    if not ins or not outs:
        raise SystemExit(f"No two-way '{match}' device found. Pair the phone, start a call, route its audio to the PC, then retry. Run --list-devices to inspect.")
    rate = int(devs[ins[0]]["default_samplerate"])
    return ins[0], outs[0], rate


def list_devices() -> None:
    import sounddevice as sd

    for i, d in enumerate(sd.query_devices()):
        print(f"{i:>3} | {d['name']} | in:{d['max_input_channels']} out:{d['max_output_channels']} | {int(d['default_samplerate'])} Hz")


# --------------------------------------------------------------------------- the conversation
class PriyaCall:
    def __init__(self, path, stt, tts, voices, *, persona, facts, contact, business, language="auto", max_turns=16, barge_in=True):  # type: ignore[no-untyped-def]
        from sellagent_speech.pipeline import BargeInMonitor
        from sellagent_speech.vad import VadConfig

        self.path, self.stt, self.tts, self.voices = path, stt, tts, voices
        self.persona, self.facts = persona, facts
        self.contact, self.business, self.language = contact, business, language
        self.max_turns, self.barge_in = max_turns, barge_in
        self.engine = ConversationEngine(None, use_llm=False)
        self.memory = ConversationMemory()
        self.ctx = ConversationContext(authorized=True)
        self.sm = ConversationStateMachine(State.CONNECTED)
        self.transcript: list[dict] = []
        self.outcome: str | None = None
        self.stopped = False
        self.sleep = time.sleep  # tests set a no-op to run silence windows instantly
        self._BargeInMonitor, self._VadConfig = BargeInMonitor, VadConfig

    def stop(self, reason: str = "operator stop") -> None:
        self.stopped = True
        self.ctx.emergency_stop = True
        print(f"\n[STOP] {reason}")

    def _resample(self, a, src, dst):  # type: ignore[no-untyped-def]
        from sellagent_speech.audio_io import resample

        return resample(np.asarray(a, dtype=np.float32), src, dst)

    def speak(self, text: str, lang: str) -> bool:
        if not text or self.stopped:
            return True
        voice = self.voices.get(lang) or self.voices.get("en")
        text = cscripts.gendered(text, lang, self.persona.gender)
        self.transcript.append({"speaker": "priya", "text": text, "lang": lang, "at": datetime.now(UTC).isoformat()})
        print(f"\nPRIYA ({lang}): {text}")
        out = self.tts.synthesize(text, voice, speed=1.0)
        audio = self._resample(out.audio, out.sample_rate, self.path.sample_rate)
        step = int(self.path.sample_rate * CHUNK_S)
        barge = self._BargeInMonitor(self._VadConfig(sample_rate=self.path.sample_rate, min_speech_ms=150, hangover_ms=300))
        for i in range(0, len(audio), step):
            if self.stopped or not self.path.is_open():
                return False
            self.path.write(audio[i : i + step])
            if self.barge_in:
                incoming = self.path.read()
                if len(incoming) and barge.feed(incoming):
                    self._carry = self._resample(incoming, self.path.sample_rate, SR)
                    print("   [caller interrupted]")
                    return False
        return True

    def listen(self, timeout_s: float = 8.0, max_utt_s: float = 15.0):  # type: ignore[no-untyped-def]
        from sellagent_speech.vad import EnergyVAD, VadConfig

        vad = EnergyVAD(VadConfig(sample_rate=SR, frame_ms=30, min_speech_ms=200, hangover_ms=800))
        frame = vad._frame
        pending = getattr(self, "_carry", np.zeros(0, dtype=np.float32))
        self._carry = np.zeros(0, dtype=np.float32)
        buf, started, waited, guard = [], False, 0.0, 0
        while not self.stopped and self.path.is_open():
            guard += 1
            if guard > 100_000:  # never spin forever on a stuck device
                return np.concatenate(buf) if buf else None
            chunk = self.path.read()
            if len(chunk):
                pending = np.concatenate([pending, self._resample(chunk, self.path.sample_rate, SR)])
            elif not len(pending):
                self.sleep(0.02)
                waited += 0.02
                if not started and waited > timeout_s:
                    return None
                continue
            while len(pending) >= frame:
                f, pending = pending[:frame], pending[frame:]
                if started or vad.feed(f):
                    started = True
                    buf.append(f)
                    if not vad.in_speech or len(buf) * 0.03 >= max_utt_s:
                        return np.concatenate(buf)
                else:
                    waited += 0.03
                    if waited > timeout_s:
                        return None
        return None

    def hear(self, lang: str):  # type: ignore[no-untyped-def]
        for _ in range(2):
            audio = self.listen()
            if self.stopped:
                return None, None
            if audio is None:
                return None, "silence"
            res = self.stt.transcribe(audio, language=None, allow_download=False)
            text = (res.text or "").strip()
            if text:
                self.transcript.append({"speaker": "caller", "text": text, "lang": res.language, "at": datetime.now(UTC).isoformat()})
                print(f"CALLER ({res.language}): {text}")
                return text, res.language
            self.speak(REPEAT.get(lang, REPEAT["en"]), lang)
        return None, "unrecognised"

    def run(self) -> str:
        lang = self.language if self.language in ("hi", "en") else "en"
        utterance = None
        for _ in range(self.max_turns):
            if self.stopped:
                break
            turn = self.engine.respond(self.sm, utterance, facts=self.facts, ctx=self.ctx, preferred_language=lang,
                                       contact_person=self.contact, business_name=self.business, persona=self.persona, memory=self.memory)
            lang = turn.language if turn.language in ("hi", "en") else lang
            self.memory.observe("agent", turn.agent_text)
            self.speak(turn.agent_text, lang)
            if self.sm.is_terminal:
                self.outcome = turn.outcome
                break
            text, detected = self.hear(lang)
            if text is None:
                self.outcome = "callback_requested" if detected == "silence" else "human_handoff"
                closing = {"en": "I could not hear you clearly, so a FITRON team member will call you back. Thank you.", "hi": "आवाज़ साफ़ नहीं आई, इसलिए FITRON टीम आपको वापस कॉल करेगी। धन्यवाद।"}
                self.speak(closing.get(lang, closing["en"]), lang)
                break
            if detected in ("hi", "en"):
                lang = detected
            self.memory.observe("prospect", text)
            utterance = text
        else:
            self.outcome = self.outcome or "max_turns"
        return self.outcome or "ended"


# --------------------------------------------------------------------------- selftest (no hardware/models)
def selftest() -> int:
    """Prove Priya's conversation brain deterministically with a scripted caller - no phone, no Bluetooth, no
    downloads. Drives the same engine/persona/facts the live call uses, asserting AI disclosure, approved-price-
    only, language switching and opt-out. The real duplex audio path is covered by
    tests/integration/test_media_gateway.py; this checks what Priya SAYS."""
    engine = ConversationEngine(None, use_llm=False)
    facts = approved_fitron_facts()
    persona = Persona()

    def converse(scripted):  # type: ignore[no-untyped-def]
        sm = ConversationStateMachine(State.CONNECTED)
        mem = ConversationMemory()
        ctx = ConversationContext(authorized=True)
        said, lang = [], "en"
        utterance = None
        for _ in range(16):
            turn = engine.respond(sm, utterance, facts=facts, ctx=ctx, preferred_language=lang, contact_person="Rahul", business_name="Power Gym", persona=persona, memory=mem)
            lang = turn.language if turn.language in ("hi", "en") else lang
            mem.observe("agent", turn.agent_text)
            said.append(turn.agent_text)
            if sm.is_terminal:
                return said, turn.outcome
            if not scripted:
                return said, turn.outcome
            utterance = scripted.pop(0)
            if turn.language == "en" and any("ऀ" <= ch <= "ॿ" for ch in utterance):
                lang = "hi"
            mem.observe("prospect", utterance)
        return said, None

    said, _ = converse(["yes this is Rahul", "yes go ahead", "we use excel", "pending payments are hard to track", "कीमत कितनी है"])
    blob = " ".join(said)
    disclosed = "AI assistant" in blob
    priced = "₹1,999" in blob
    hindi = "बोल रही हूँ" in blob or any("ऀ" <= ch <= "ॿ" for ch in blob)
    no_bad = "₹499" not in blob and "₹1,000" not in blob  # unapproved offer stays out
    # opt-out wins immediately
    said2, out2 = converse(["I'm busy, don't call me again"])
    opt_out = out2 == "opted_out"
    print(f"\nselftest: turns={len(said)} ai_disclosed={disclosed} approved_price={priced} hindi_switch={hindi} no_unapproved_price={no_bad} opt_out_respected={opt_out}")
    ok = disclosed and priced and hindi and no_bad and opt_out
    print("SELFTEST OK" if ok else "SELFTEST FAILED")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Run Priya over Bluetooth hands-free call audio")
    ap.add_argument("--selftest", action="store_true", help="prove the wiring with fake audio/models (no phone)")
    ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--consent", action="store_true", help="REQUIRED for a real call: the other party agreed to talk to an AI")
    ap.add_argument("--dial", default=None, help="optional: place the call to this number via ADB (consented test number)")
    ap.add_argument("--adb", default="adb")
    ap.add_argument("--match", default="HF Audio", help="substring of the phone's hands-free audio device name")
    ap.add_argument("--contact", default="")
    ap.add_argument("--business", default="")
    ap.add_argument("--language", default="auto", choices=["auto", "hi", "en"])
    ap.add_argument("--whisper", default="small")
    ap.add_argument("--models-dir", default=None)
    ap.add_argument("--voice-en", default=None)
    ap.add_argument("--voice-hi", default=None)
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if a.list_devices:
        list_devices()
        return 0
    if not a.consent:
        print("Refusing to run a real call without --consent. This tool is for ONE consenting participant, not bulk dialing.\nSee docs/BLUETOOTH_AUDIO.md. Use --selftest to check the setup safely.")
        return 2

    from sellagent_backend.config import Settings
    from sellagent_backend.telecom.local_audio import LocalAudioTransport
    from sellagent_backend.telecom.media_gateway import SipRtpCallAudioPath
    from sellagent_speech import FasterWhisperSTT, PiperTTS

    models_dir = Path(a.models_dir) if a.models_dir else Settings().models_dir
    stt = FasterWhisperSTT(a.whisper, models_dir=models_dir)
    ok, msg = stt.available()
    if not ok:
        print(f"Speech recognition not ready: {msg}\nInstall models: python scripts/download_models.py --whisper {a.whisper} --piper hi_IN-priyamvada-medium en_US-lessac-medium --yes")
        return 3
    tts = PiperTTS(models_dir)
    ok, msg = tts.available()
    if not ok:
        print(f"Voice (Piper) not ready: {msg}\nInstall a Hindi + English voice with scripts/download_models.py.")
        return 3
    voices = {"en": a.voice_en or "en_US-lessac-medium", "hi": a.voice_hi or "hi_IN-priyamvada-medium"}

    in_i, out_i, rate = find_hf_devices(a.match)
    print(f"Using Bluetooth call audio: in={in_i} out={out_i} rate={rate} Hz")
    transport = LocalAudioTransport(in_i, out_i, samplerate=rate)
    if not transport.start():
        print("Could not open the Bluetooth audio devices. Be in a live call with audio routed to the PC, then retry.")
        return 4
    path = SipRtpCallAudioPath(transport=transport)

    phone = Phone(a.adb)
    if a.dial:
        print(f"Dialing {a.dial} …")
        phone.dial(a.dial)
        for _ in range(30):
            if phone.call_state() == "IN_CALL":
                break
            time.sleep(1)
        if phone.call_state() != "IN_CALL":
            print("Call did not connect. Make sure the phone routes call audio to the PC.")

    call = PriyaCall(path, stt, tts, voices, persona=Persona(), facts=approved_fitron_facts(),
                     contact=a.contact, business=a.business, language=a.language)

    import signal

    signal.signal(signal.SIGINT, lambda *_: call.stop("Ctrl-C emergency stop"))
    print("Priya is on the line. Press Ctrl-C for emergency stop.\n")
    try:
        outcome = call.run()
    finally:
        path.close()
        if a.dial:
            phone.hang_up()
    rec = {"at": datetime.now(UTC).isoformat(), "contact": a.contact, "business": a.business, "outcome": outcome, "transcript": call.transcript}
    out = _ROOT / "priya_calls"
    out.mkdir(exist_ok=True)
    f = out / f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.json"
    f.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    print(f"\nOutcome: {outcome}. Transcript saved to {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
