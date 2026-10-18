"""AI voice bridge (PC speaker + mic next to the phone on speakerphone), driven with scripted replies instead of
real audio. These prove the conversation/safety logic; they say nothing about real call audio quality."""

from __future__ import annotations

import threading

import pytest
from conftest import make_contact, open_hours


class FakeSpeaker:
    def __init__(self) -> None:
        self.said: list[tuple[str, str]] = []

    def speak(self, text: str, language: str) -> float:
        self.said.append((text, language))
        return 1.0


class FakeListener:
    """Returns the scripted replies in order; None = silence. Optionally blocks until released."""

    def __init__(self, replies: list[str | None], gate: threading.Event | None = None) -> None:
        self.replies = list(replies)
        self.gate = gate
        self.calls = 0

    def listen(self, *, timeout_s, max_utterance_s, language, should_stop):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.gate is not None:
            while not self.gate.wait(0.05):
                if should_stop():
                    return None
        return self.replies.pop(0) if self.replies else None


def _setup(client, **contact):  # type: ignore[no-untyped-def]
    open_hours(client)
    assert client.patch("/api/v1/settings", json={"values": {"bridge.enabled": True, "privacy.allow_live_transcription": True}}).status_code == 200
    c = make_contact(client, **contact)
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"], "route": "manual"}).json()
    call_id = client.post(f"/api/v1/call-jobs/{job['id']}/dispatch").json()["call_id"]
    assert client.post(f"/api/v1/calls/{call_id}/connected").status_code == 200
    return c, job, call_id


def _use(client, speaker, listener) -> None:  # type: ignore[no-untyped-def]
    client.app.state.bridge.audio_factory = lambda _s: (speaker, listener)
    client.app.state.bridge.stop_audio = lambda: None


def _run(client, call_id: str, **body):  # type: ignore[no-untyped-def]
    r = client.post(f"/api/v1/calls/{call_id}/bridge/start", json={"language": "en", "use_llm": False, **body})
    assert r.status_code == 200, r.text
    session = client.app.state.bridge.active
    assert session is not None and session.wait(10)
    return session


def test_bridge_full_conversation_after_spoken_consent(client):
    _c, job, call_id = _setup(client)
    speaker = FakeSpeaker()
    _use(client, speaker, FakeListener(["yes that's fine", "yes this is Rahul", "yes go ahead", "we use excel", "demo please", "tomorrow at 5 pm", "okay thanks"]))
    session = _run(client, call_id)
    assert session.status == "finished", session.to_dict()
    assert session.error is None and session.prospect_utterances >= 5
    said = " ".join(t for t, _ in speaker.said)
    assert "automated AI assistant" in said and "yes or no" in said  # AI identity + consent question first
    assert "₹1,999" in said  # price only from approved knowledge
    detail = client.get(f"/api/v1/calls/{call_id}").json()
    prospect = [t for t in detail["transcript"] if t["speaker"] == "prospect"]
    assert prospect and all(t["source"] == "stt" for t in prospect)
    assert client.get(f"/api/v1/call-jobs/{job['id']}").json()["status"] == "completed"
    assert detail["call"]["outcome"] is not None
    # a supervised bridge call is recorded as pending evidence for the operator, never auto-confirmed
    rows = [r for r in client.get("/api/v1/audio-tests").json() if r["step"] == "acoustic_bridge_call"]
    assert len(rows) == 1 and rows[0]["status"] == "pass" and rows[0]["operator_confirmed"] is False
    # and it does NOT open the autonomous release gate
    assert client.get("/api/v1/settings/release-gate").json()["allowed"] is False


def test_bridge_stops_when_prospect_declines_or_opts_out(client):
    _c, job, call_id = _setup(client)
    speaker = FakeSpeaker()
    _use(client, speaker, FakeListener(["no"]))
    session = _run(client, call_id)
    assert session.outcome == "not_interested" and session.prospect_utterances == 1
    assert client.get(f"/api/v1/calls/{call_id}").json()["call"]["outcome"] == "not_interested"
    # declined consent: the reply is not stored as a transcript line
    assert not [t for t in client.get(f"/api/v1/calls/{call_id}").json()["transcript"] if t["speaker"] == "prospect"]

    c2, _job2, call2 = _setup(client, business_name="Iron Gym", phone="9123456781")
    _use(client, FakeSpeaker(), FakeListener(["please do not call me again"]))
    session = _run(client, call2)
    assert session.outcome == "opted_out"
    assert client.get(f"/api/v1/contacts/{c2['id']}").json()["opted_out"] is True


def test_bridge_ends_politely_on_silence(client):
    _c, _job, call_id = _setup(client)
    speaker = FakeSpeaker()
    _use(client, speaker, FakeListener([None, None]))
    session = _run(client, call_id)
    assert session.outcome == "no_answer" and "could not hear a reply" in speaker.said[-1][0]


def test_bridge_preconditions(client):
    _c, _job, call_id = _setup(client)
    _use(client, FakeSpeaker(), FakeListener([]))
    client.patch("/api/v1/settings", json={"values": {"bridge.enabled": False}})
    r = client.post(f"/api/v1/calls/{call_id}/bridge/start", json={})
    assert r.status_code == 400 and r.json()["code"] == "bridge_disabled"
    client.patch("/api/v1/settings", json={"values": {"bridge.enabled": True, "privacy.allow_live_transcription": False}})
    assert client.post(f"/api/v1/calls/{call_id}/bridge/start", json={}).json()["code"] == "transcription_disabled"
    client.patch("/api/v1/settings", json={"values": {"privacy.allow_live_transcription": True}})
    # the AI only talks to contacts who agreed to be called
    _c2, _j2, call2 = _setup(client, business_name="Cold Gym", phone="9123456782")
    from sellagent_backend.db.models import Call, Contact

    with client.app.state.session_factory() as s:
        contact = s.get(Contact, s.get(Call, call2).contact_id)
        contact.consent_status = "unknown"
        s.commit()
    assert client.post(f"/api/v1/calls/{call2}/bridge/start", json={}).json()["code"] == "contact_not_allowed"
    # not a live call
    assert client.post("/api/v1/calls/nope/bridge/start", json={}).json()["code"] == "not_found"


@pytest.mark.parametrize("how", ["take_over", "emergency_stop"])
def test_operator_can_always_stop_the_ai(client, how):
    _c, job, call_id = _setup(client)
    gate = threading.Event()
    _use(client, FakeSpeaker(), FakeListener(["yes"], gate=gate))
    assert client.post(f"/api/v1/calls/{call_id}/bridge/start", json={"language": "en", "use_llm": False}).status_code == 200
    # one call at a time
    assert client.post(f"/api/v1/calls/{call_id}/bridge/start", json={}).json()["code"] == "busy"
    if how == "take_over":
        assert client.post(f"/api/v1/calls/{call_id}/bridge/stop").status_code == 200
    else:
        assert client.post("/api/v1/call-jobs/emergency-stop", json={"reason": "test"}).status_code == 200
    session = client.app.state.bridge.active
    assert session.wait(5) and session.status == "stopped"
    if how == "take_over":
        # the call stays with the operator
        assert client.get(f"/api/v1/call-jobs/{job['id']}").json()["status"] == "in_progress"
    status = client.get("/api/v1/calls/bridge/status").json()
    assert status["active"] is None and status["last"]["status"] == "stopped"
