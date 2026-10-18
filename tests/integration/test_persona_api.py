"""Persona through the real call console API (script mode): name + AI disclosure, Hindi feminine speech, memory
returned per turn, cue-driven turns, settings validation and that disabling the persona restores the default."""

from __future__ import annotations

from conftest import make_contact, open_hours


def _call(client) -> str:  # type: ignore[no-untyped-def]
    open_hours(client)
    c = make_contact(client)
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"], "route": "manual"}).json()
    call_id = client.post(f"/api/v1/call-jobs/{job['id']}/dispatch").json()["call_id"]
    client.post(f"/api/v1/calls/{call_id}/connected")
    return call_id


def _step(client, call_id, text, lang="en"):  # type: ignore[no-untyped-def]
    r = client.post(f"/api/v1/calls/{call_id}/step", json={"utterance": text, "language": lang, "use_llm": False})
    assert r.status_code == 200, r.text
    return r.json()


def test_persona_conversation_with_memory_and_cues(client):
    assert client.patch("/api/v1/settings", json={"values": {"persona.name": "Ananya"}}).status_code == 200
    call_id = _call(client)
    g = _step(client, call_id, None)
    assert "Ananya" in g["agent_text"] and "AI assistant" in g["agent_text"] and g["persona"] == "Ananya"
    _step(client, call_id, "yes this is Rahul")
    _step(client, call_id, "yes go ahead")
    t = _step(client, call_id, "we use tally for member fees")
    # asks what to improve, but never names Tally: that could imply an integration claim the guardrails forbid
    assert "existing_software" in t["cues"] and "improve" in t["agent_text"] and "tally" not in t["agent_text"].lower()
    t = _step(client, call_id, "renewal reminders and pending payments")
    assert t["state"] == "product_explanation" and "₹1,999" in t["agent_text"]
    assert "currently uses: tally" in t["memory"]
    t = _step(client, call_id, "sorry, I didn't understand")
    assert t["state"] == "product_explanation" and "In short" in t["agent_text"]


def test_hindi_persona_speaks_in_feminine_form(client):
    call_id = _call(client)
    g = _step(client, call_id, None, lang="hi")
    assert "Priya" in g["agent_text"] and "बोल रही हूँ" in g["agent_text"]
    t = _step(client, call_id, "अभी समय नहीं है, बाद में", lang="hi")
    assert t["state"] in ("followup_scheduling", "permission_to_continue") and "रहा हूँ" not in t["agent_text"]


def test_persona_settings_validation_and_disable(client):
    bad = {"persona.style": "pushy", "persona.gender": "x", "persona.volume_percent": 300, "persona.memory_turns": 99, "persona.name": "", "persona.handoff": "hangup"}
    for k, v in bad.items():
        assert client.patch("/api/v1/settings", json={"values": {k: v}}).status_code == 400, k
    assert client.patch("/api/v1/settings", json={"values": {"persona.enabled": False}}).status_code == 200
    call_id = _call(client)
    g = _step(client, call_id, None)
    assert g["persona"] is None and "this is an automated AI assistant" in g["agent_text"]
