"""Exotel AgentStream provider (production route): the bidirectional streaming transport, fail-closed gating,
the dial adapter, and the token-authenticated WebSocket bridge. All simulated - no Exotel account, no real call.
It proves the plumbing and safety, NOT that a real Exotel call works (that needs the user's account + a real
consented test; see docs/PRODUCTION_READINESS.md)."""

from __future__ import annotations

import json

import numpy as np
import pytest
from conftest import make_contact, open_hours
from sellagent_backend.telecom.exotel import (
    ExotelStreamTransport,
    decode_media_event,
    encode_media_event,
    pcm_from_float,
)

pytestmark = pytest.mark.simulated


def test_media_event_round_trip_and_rechunk():
    pcm = pcm_from_float(np.full(320, 0.1, dtype=np.float32))
    ev = encode_media_event(pcm, "sid")
    assert ev["event"] == "media" and decode_media_event(ev) == pcm
    assert decode_media_event({"event": "stop"}) is None
    t = ExotelStreamTransport(sample_rate=8000)  # 320-byte frames
    t.feed_inbound(b"\x00" * 800)  # two whole frames, 160 bytes carried
    assert len(t.recv()) == 320 and len(t.recv()) == 320 and t.recv() is None
    t.send(b"\x01" * 320)
    assert t.drain_outbound() == [b"\x01" * 320]
    t.request_clear()
    assert t.take_clear() is True and t.take_clear() is False


def _enable(client, *, creds=True, stream=True) -> None:  # type: ignore[no-untyped-def]
    import os

    if creds:
        os.environ.update(EXOTEL_API_KEY="k", EXOTEL_API_TOKEN="t", EXOTEL_SID="sid", EXOTEL_STREAM_TOKEN="secret")
    vals = {"provider.enabled": True, "provider.kind": "exotel", "provider.caller_id": "08012345678"}
    if stream:
        vals["provider.stream_public_url"] = "wss://tunnel.example/api/v1/exotel/stream"
    assert client.patch("/api/v1/settings", json={"values": vals}).status_code == 200


def _open_gate(client) -> None:  # type: ignore[no-untyped-def]
    for step, direction, ev in (("remote_speech_capture", "inbound", {"remote_capture_possible": "true"}), ("generated_speech_transmission", "outbound", {"uplink_injection": "digital"})):
        r = client.post("/api/v1/audio-tests", json={"test_id": "EXO", "step": step, "direction": direction, "status": "pass", "kind": "real_device", "evidence": ev}).json()
        assert client.post(f"/api/v1/audio-tests/{r['id']}/confirm").status_code == 200


def test_caller_id_is_provider_exophone_not_jio(client):
    adapter = client.app.state.telecom["exotel"]
    _enable(client)
    seen = {}

    async def fake_post(*, payload, creds):  # type: ignore[no-untyped-def]
        seen.update(payload)
        return True, "ok"

    adapter.http_post = fake_post
    open_hours(client)
    c = make_contact(client, phone="9123456780")
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"], "route": "exotel"}).json()
    r = client.post(f"/api/v1/call-jobs/{job['id']}/dispatch")
    assert r.status_code == 200, r.text
    assert seen["From"] == "08012345678" and seen["CallerId"] == "08012345678"  # ExoPhone, not the Jio number
    assert seen["To"].endswith("9123456780") and "call_id=" in seen["StreamUrl"]


def test_dial_refused_without_config(client):
    # provider disabled -> eligibility blocks the job before dialing
    open_hours(client)
    c = make_contact(client)
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"], "route": "exotel"}).json()
    assert job["status"] == "blocked" and "provider is not enabled" in " ".join(job["eligibility_result"]["reasons"])
    caps = client.get("/api/v1/call-jobs/routes").json()["exotel"]
    assert caps["can_dial"] is False and caps["autonomous_supported"] is False


def test_path_is_fail_closed(client):
    adapter = client.app.state.telecom["exotel"]
    _enable(client)

    async def fake_post(*, payload, creds):  # type: ignore[no-untyped-def]
        return True, "ok"

    adapter.http_post = fake_post
    open_hours(client)
    c = make_contact(client)
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"], "route": "exotel"}).json()
    call_id = client.post(f"/api/v1/call-jobs/{job['id']}/dispatch").json()["call_id"]
    t = ExotelStreamTransport()
    # 1) gate closed -> no path even with a connected stream
    adapter.bind(call_id, t)
    assert adapter.call_audio_path(call_id) is None
    # 2) gate open, stream bound -> a verified path
    _open_gate(client)
    assert adapter.call_audio_path(call_id) is not None
    # 3) stream gone -> no path
    adapter.unbind(call_id)
    assert adapter.call_audio_path(call_id) is None


def _dispatched_call(client):  # type: ignore[no-untyped-def]
    adapter = client.app.state.telecom["exotel"]

    async def fake_post(*, payload, creds):  # type: ignore[no-untyped-def]
        return True, "ok"

    adapter.http_post = fake_post
    open_hours(client)
    c = make_contact(client)
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"], "route": "exotel"}).json()
    return client.post(f"/api/v1/call-jobs/{job['id']}/dispatch").json()["call_id"]


def test_ws_rejects_without_token(client):
    _enable(client)
    call_id = _dispatched_call(client)
    with pytest.raises(Exception):  # noqa: B017 - starlette raises on the denied handshake
        with client.websocket_connect(f"/api/v1/exotel/stream?call_id={call_id}") as ws:
            ws.receive_text()


def test_ws_binds_and_receives_caller_audio(client):
    adapter = client.app.state.telecom["exotel"]
    _enable(client)
    call_id = _dispatched_call(client)
    pcm = pcm_from_float(np.full(160, 0.2, dtype=np.float32))  # one 8 kHz 20 ms frame = 160 samples
    with client.websocket_connect(f"/api/v1/exotel/stream?token=secret&call_id={call_id}&sample-rate=8000") as ws:
        ws.send_text(json.dumps({"event": "start", "stream_sid": "s1"}))
        ws.send_text(json.dumps(encode_media_event(pcm, "s1")))  # caller -> AI
        import time

        got = None
        for _ in range(100):
            t = adapter.transport_for(call_id)
            if t is not None:
                got = t.recv()
                if got is not None:
                    break
            time.sleep(0.02)
        assert got == pcm  # the caller's audio reached the bound transport
        ws.send_text(json.dumps({"event": "stop"}))
    for _ in range(50):
        if adapter.transport_for(call_id) is None:
            break
        import time

        time.sleep(0.02)
    assert adapter.transport_for(call_id) is None  # unbound on stop/close
