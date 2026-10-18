"""Autonomous conversation loop - SIMULATED: a fake digital call-audio path and fake STT/TTS stand in for a verified
route. Proves the loop's logic and safety (gates, barge-in, language switching, opt-out, silence, poor recognition,
emergency stop). It is NOT evidence that any real phone route provides call audio; the real Android/Jio adapter
returns no path, which the first test checks."""

from __future__ import annotations

import time
from types import SimpleNamespace

import numpy as np
import pytest
from conftest import make_contact, open_hours

pytestmark = pytest.mark.simulated
SR = 16000


def _tone(seconds: float) -> np.ndarray:
    t = np.linspace(0, seconds, int(SR * seconds), endpoint=False)
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


class FakePath:
    """Caller script items: "text" (answers after the AI finishes), ("text", "interrupt") (talks over the AI),
    None (stays silent for one listening window)."""

    name = "simulated-digital-path"
    sample_rate = SR

    def __init__(self, script: list) -> None:  # type: ignore[type-arg]
        self.script = list(script)
        self.buf = np.zeros(0, dtype=np.float32)
        self.said: list[str] = []  # what the caller said, in order (consumed by FakeSTT)
        self.written = 0
        self.open = True
        self.empty_reads = 0

    def _load(self) -> None:
        item = self.script.pop(0)
        text = item[0] if isinstance(item, tuple) else item
        self.said.append(text)
        self.buf = np.concatenate([self.buf, _tone(0.8), np.zeros(int(SR * 1.2), dtype=np.float32)])

    def write(self, chunk) -> None:  # type: ignore[no-untyped-def]
        self.written += len(chunk)
        if not len(self.buf) and self.script and isinstance(self.script[0], tuple) and self.script[0][1] == "interrupt" and self.written > SR * 0.3:
            self._load()

    def read(self) -> np.ndarray:
        if not len(self.buf) and self.script:
            if self.script[0] is None:
                self.empty_reads += 1
                if self.empty_reads > 450:  # > 8 s of fake time
                    self.script.pop(0)
                    self.empty_reads = 0
                return np.zeros(0, dtype=np.float32)
            if not isinstance(self.script[0], tuple):
                self._load()
        out, self.buf = self.buf[:1600], self.buf[1600:]
        return out

    def is_open(self) -> bool:
        return self.open

    def close(self) -> None:
        self.open = False


class FakeSTT:
    def __init__(self, path: FakePath, garble: bool = False) -> None:
        self.path, self.garble = path, garble

    def transcribe(self, audio, *, language=None, allow_download=False):  # type: ignore[no-untyped-def]
        text = "" if self.garble else (self.path.said.pop(0) if self.path.said else "")
        lang = "hi" if any("ऀ" <= ch <= "ॿ" for ch in text) else "en"
        return SimpleNamespace(text=text, language=lang)


class FakeTTS:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str, float]] = []

    def synthesize(self, text, voice, speed=1.0, **_kw):  # type: ignore[no-untyped-def]
        self.lines.append((text, voice, speed))
        return SimpleNamespace(audio=np.zeros(int(22050 * 1.5), dtype=np.float32), sample_rate=22050)


def _open_gate(client) -> None:  # type: ignore[no-untyped-def]
    """Simulated evidence rows so the gate logic can be exercised; never produced by the real phone route."""
    for step, direction, ev in (("remote_speech_capture", "inbound", {"remote_capture_possible": "true"}), ("generated_speech_transmission", "outbound", {"uplink_injection": "digital"})):
        r = client.post("/api/v1/audio-tests", json={"test_id": "SIM-GATE", "step": step, "direction": direction, "status": "pass", "kind": "real_device", "evidence": ev}).json()
        assert client.post(f"/api/v1/audio-tests/{r['id']}/confirm").status_code == 200
    assert client.get("/api/v1/settings/release-gate").json()["allowed"] is True
    assert client.patch("/api/v1/settings", json={"values": {"calling.autonomous_enabled": True, "privacy.allow_live_transcription": True, "ai.tts_speed_percent": 110}}).status_code == 200


def _live_call(client, **contact) -> tuple[dict, str]:  # type: ignore[no-untyped-def]
    open_hours(client)
    c = make_contact(client, **contact)
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"], "route": "manual"}).json()
    call_id = client.post(f"/api/v1/call-jobs/{job['id']}/dispatch").json()["call_id"]
    assert client.post(f"/api/v1/calls/{call_id}/connected").status_code == 200
    return c, call_id


def _use(client, path: FakePath, *, garble: bool = False) -> FakeTTS:  # type: ignore[no-untyped-def]
    tts = FakeTTS()
    client.app.state.telecom["manual"].call_audio_path = lambda _cid: path
    client.app.state.autonomy.components = lambda _s: (FakeSTT(path, garble), tts, {"en": "en-voice", "hi": "hi-voice"})
    client.app.state.autonomy.sleep = lambda _s: None
    return tts


def _run(client, call_id: str):  # type: ignore[no-untyped-def]
    r = client.post(f"/api/v1/calls/{call_id}/autonomy/start", json={"language": "en", "use_llm": False})
    assert r.status_code == 200, r.text
    s = client.app.state.autonomy.active
    assert s.wait(20), s.to_dict()
    return s


def test_real_routes_have_no_verified_audio_path_and_gate_is_required(client):
    _c, call_id = _live_call(client)
    r = client.post(f"/api/v1/calls/{call_id}/autonomy/start", json={})
    assert r.status_code == 400 and r.json()["code"] == "release_gate_closed"
    _open_gate(client)
    # gate open, but the manual route (and the Android/Jio route) provide no digital call-audio path
    r = client.post(f"/api/v1/calls/{call_id}/autonomy/start", json={})
    assert r.status_code == 400 and r.json()["code"] == "no_verified_audio_path"
    assert client.app.state.telecom["android_companion"].call_audio_path(call_id) is None


def test_full_conversation_with_barge_in_and_language_switch(client):
    _open_gate(client)
    _c, call_id = _live_call(client)
    path = FakePath(["yes this is Rahul", "yes go ahead", "we use excel", ("कीमत कितनी है", "interrupt"), "demo please", "kal shaam paanch baje", "ok thank you"])
    tts = _use(client, path)
    s = _run(client, call_id)
    assert s.status == "finished", s.to_dict()
    assert s.interruptions >= 1  # caller talked over the AI; the rest of that line was cancelled
    assert "hi" in s.languages  # followed the caller into Hindi
    said = " ".join(t for t, _, _ in tts.lines)
    assert "automated AI assistant" in said and "₹1,999" in said
    assert all(speed == pytest.approx(1.1) for _, _, speed in tts.lines)
    assert any(voice == "hi-voice" for _, voice, _ in tts.lines)
    d = client.get(f"/api/v1/calls/{call_id}").json()
    prospect = [t for t in d["transcript"] if t["speaker"] == "prospect"]
    assert len(prospect) >= 5 and all(t["source"] == "stt" for t in prospect)
    assert d["call"]["outcome"] is not None


def test_opt_out_stops_and_records(client):
    _open_gate(client)
    c, call_id = _live_call(client)
    _use(client, FakePath(["please do not call me again"]))
    s = _run(client, call_id)
    assert s.outcome == "opted_out"
    assert client.get(f"/api/v1/contacts/{c['id']}").json()["opted_out"] is True


def test_silence_and_unreliable_recognition_fall_back_safely(client):
    _open_gate(client)
    _c, call_id = _live_call(client)
    tts = _use(client, FakePath([None, None]))
    s = _run(client, call_id)
    assert s.outcome == "callback_requested" and "could not hear" in tts.lines[-1][0]
    _c2, call2 = _live_call(client, business_name="Noisy Gym", phone="9123456783")
    _use(client, FakePath(["mumble", "mumble"]), garble=True)
    s = _run(client, call2)
    assert s.outcome == "human_handoff" and "recognition unreliable" in s.reason


def test_emergency_stop_and_consent_gate(client):
    _open_gate(client)
    _c, call_id = _live_call(client)
    _use(client, FakePath([None, None, None, None]))
    client.app.state.autonomy.sleep = time.sleep  # real 8 s listening windows: the stop must land mid-call
    assert client.post(f"/api/v1/calls/{call_id}/autonomy/start", json={"language": "en", "use_llm": False}).status_code == 200
    assert client.post(f"/api/v1/calls/{call_id}/autonomy/start", json={}).json()["code"] == "busy"
    assert client.post("/api/v1/call-jobs/emergency-stop", json={"reason": "test"}).status_code == 200
    s = client.app.state.autonomy.active
    assert s.wait(10) and s.status == "stopped"
    # contacts without granted consent are never handed to the AI
    from sellagent_backend.db.models import Call, Contact

    with client.app.state.session_factory() as db:
        db.get(Contact, db.get(Call, call_id).contact_id).consent_status = "unknown"
        db.commit()
    from sellagent_backend.services import settings_service

    with client.app.state.session_factory() as db:
        settings_service.set_value(db, "calling.emergency_stop_active", False, force_internal=True)
        db.commit()
    assert client.post(f"/api/v1/calls/{call_id}/autonomy/start", json={}).json()["code"] in ("contact_not_allowed", "not_live")
