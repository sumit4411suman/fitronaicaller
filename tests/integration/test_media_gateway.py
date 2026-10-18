"""Modular audio gateway (calling Approach C). Proves the PCM path/transport logic and that the route is
fail-closed: it hands the autonomous loop a verified digital path ONLY when the release gate is satisfied by
real-device evidence, the gateway is switched on, AND a gateway is actually bound to the call. The transport here
is an in-memory loopback standing in for an external qualified gateway (a dedicated Qualcomm GSM<->SIP phone or a
licensed SIP trunk); it is NOT evidence that the S25/Jio route can do this - that route binds nothing."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from conftest import make_contact, open_hours
from sellagent_backend.telecom.media_gateway import (
    BYTES_PER_FRAME,
    SAMPLES_PER_FRAME,
    LoopbackTransport,
    MediaGatewayAdapter,
    SipRtpCallAudioPath,
)

pytestmark = pytest.mark.simulated
SILENCE = b"\x00" * BYTES_PER_FRAME


def _tone_frame() -> bytes:
    return (0.25 * np.sin(np.linspace(0, 6.0, SAMPLES_PER_FRAME)) * 32767).astype("<i2").tobytes()


# --------------------------------------------------------------------------- transport / path
def test_path_round_trip_and_frame_discipline():
    app, gw = LoopbackTransport.pair()
    path = SipRtpCallAudioPath(transport=app, pace=lambda _s: None)
    # AI writes 60 ms of audio -> exactly 3 x 640-byte frames reach the gateway side
    path.write(np.full(SAMPLES_PER_FRAME * 3, 0.1, dtype=np.float32))
    got = []
    while (f := gw.recv()) is not None:
        got.append(f)
    assert len(got) == 3 and all(len(f) == BYTES_PER_FRAME for f in got)
    # caller audio comes back as float32 mono in range
    gw.send(_tone_frame())
    back = path.read()
    assert back.dtype == np.float32 and back.shape[0] == SAMPLES_PER_FRAME and np.abs(back).max() <= 1.0


def test_inbound_jitter_buffer_is_bounded_and_drops_oldest():
    app, gw = LoopbackTransport.pair(maxlen=10_000)
    path = SipRtpCallAudioPath(transport=app, pace=lambda _s: None, jitter_frames=50)
    for _ in range(1_000):  # a flood from a stalled consumer must not grow without bound
        gw.send(SILENCE)
    out = path.read()
    assert out.shape[0] == 50 * SAMPLES_PER_FRAME  # capped at jitter_frames, oldest dropped


def test_partial_frames_are_ignored_not_fatal():
    app, gw = LoopbackTransport.pair()
    path = SipRtpCallAudioPath(transport=app, pace=lambda _s: None)
    gw.send(b"\x01\x02\x03")  # garbage / partial
    gw.send(SILENCE)
    assert path.read().shape[0] == SAMPLES_PER_FRAME  # only the valid frame survived


def test_close_and_peer_disconnect_end_the_path():
    app, gw = LoopbackTransport.pair()
    path = SipRtpCallAudioPath(transport=app, pace=lambda _s: None)
    assert path.is_open()
    gw.close()
    assert not path.is_open()  # peer gone
    path.write(np.full(SAMPLES_PER_FRAME, 0.1, dtype=np.float32))  # writing after close is a safe no-op
    app2, gw2 = LoopbackTransport.pair()
    p2 = SipRtpCallAudioPath(transport=app2, pace=lambda _s: None)
    p2.close()
    assert not p2.is_open()


# --------------------------------------------------------------------------- gating via the API
def _open_gate(client) -> None:  # type: ignore[no-untyped-def]
    for step, direction, ev in (("remote_speech_capture", "inbound", {"remote_capture_possible": "true"}), ("generated_speech_transmission", "outbound", {"uplink_injection": "digital"})):
        r = client.post("/api/v1/audio-tests", json={"test_id": "GW-GATE", "step": step, "direction": direction, "status": "pass", "kind": "real_device", "evidence": ev}).json()
        assert client.post(f"/api/v1/audio-tests/{r['id']}/confirm").status_code == 200
    assert client.patch("/api/v1/settings", json={"values": {"calling.autonomous_enabled": True, "privacy.allow_live_transcription": True}}).status_code == 200


def _live_call(client, **contact):  # type: ignore[no-untyped-def]
    open_hours(client)
    c = make_contact(client, **contact)
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"], "route": "media_gateway"}).json()
    call_id = client.post(f"/api/v1/call-jobs/{job['id']}/dispatch").json()["call_id"]
    assert client.post(f"/api/v1/calls/{call_id}/connected").status_code == 200
    return c, call_id


def test_route_is_fail_closed_until_gate_enabled_and_gateway_bound(client):
    adapter: MediaGatewayAdapter = client.app.state.telecom["media_gateway"]
    assert client.patch("/api/v1/settings", json={"values": {"gateway.enabled": True}}).status_code == 200
    _c, call_id = _live_call(client)  # human-assisted dispatch works with the gateway on, gate still closed
    app_t, _gw_t = LoopbackTransport.pair()

    # 1) gate closed -> no path even though the gateway is on and bound
    adapter.bind(call_id, app_t)
    assert adapter.call_audio_path(call_id) is None
    r = client.post(f"/api/v1/calls/{call_id}/autonomy/start", json={})
    assert r.status_code == 400 and r.json()["code"] == "release_gate_closed"

    # 2) gate open but nothing bound -> no path, loop refuses with no_verified_audio_path
    _open_gate(client)
    adapter.unbind(call_id)
    assert adapter.call_audio_path(call_id) is None
    r = client.post(f"/api/v1/calls/{call_id}/autonomy/start", json={})
    assert r.status_code == 400 and r.json()["code"] == "no_verified_audio_path"

    # 3) gate open, gateway on, transport bound -> a real verified path is returned
    adapter.bind(call_id, app_t)
    path = adapter.call_audio_path(call_id)
    assert isinstance(path, SipRtpCallAudioPath) and path.is_open()

    # 4) turning the gateway back off closes the route again
    assert client.patch("/api/v1/settings", json={"values": {"gateway.enabled": False}}).status_code == 200
    assert adapter.call_audio_path(call_id) is None


def test_gateway_bind_host_rejects_lan_exposure(client):
    bad = client.patch("/api/v1/settings", json={"values": {"gateway.bind_host": "0.0.0.0"}})  # noqa: S104 - asserting this is rejected
    assert bad.status_code == 422 or bad.status_code == 400
    assert client.patch("/api/v1/settings", json={"values": {"gateway.bind_host": "127.0.0.1"}}).status_code == 200


# --------------------------------------------------------------------------- full conversation over the route
# The autonomous loop is driven here the same proven way as tests/integration/test_autonomy.py (a float32 caller
# script), but reached THROUGH the media_gateway route and its gate. The production byte path
# (SipRtpCallAudioPath) is covered frame-by-frame by the transport tests above; this test checks the
# route -> gate -> adapter -> loop wiring end to end.
SR = 16_000


def _tone(seconds: float) -> np.ndarray:
    t = np.linspace(0, seconds, int(SR * seconds), endpoint=False)
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


class FakePath:
    name = "media-gateway"
    sample_rate = SR

    def __init__(self, script) -> None:  # type: ignore[no-untyped-def]
        self.script = list(script)
        self.buf = np.zeros(0, dtype=np.float32)
        self.said: list[str] = []
        self.written = 0
        self.open = True

    def _load(self) -> None:
        item = self.script.pop(0)
        self.said.append(item[0] if isinstance(item, tuple) else item)
        self.buf = np.concatenate([self.buf, _tone(0.8), np.zeros(int(SR * 1.2), dtype=np.float32)])

    def write(self, chunk) -> None:  # type: ignore[no-untyped-def]
        self.written += len(chunk)
        if not len(self.buf) and self.script and isinstance(self.script[0], tuple) and self.script[0][1] == "interrupt" and self.written > SR * 0.3:
            self._load()

    def read(self) -> np.ndarray:
        if not len(self.buf) and self.script and not isinstance(self.script[0], tuple):
            self._load()
        out, self.buf = self.buf[:1600], self.buf[1600:]
        return out

    def is_open(self) -> bool:
        return self.open

    def close(self) -> None:
        self.open = False


class FakeSTT:
    def __init__(self, path: FakePath) -> None:
        self.path = path

    def transcribe(self, audio, *, language=None, allow_download=False):  # type: ignore[no-untyped-def]
        text = self.path.said.pop(0) if self.path.said else ""
        lang = "hi" if any("ऀ" <= ch <= "ॿ" for ch in text) else "en"
        return SimpleNamespace(text=text, language=lang)


class FakeTTS:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str, float]] = []

    def synthesize(self, text, voice, speed=1.0, **_kw):  # type: ignore[no-untyped-def]
        self.lines.append((text, voice, speed))
        return SimpleNamespace(audio=np.zeros(int(22050 * 1.2), dtype=np.float32), sample_rate=22050)


def test_full_conversation_runs_over_the_media_gateway_route(client):
    adapter: MediaGatewayAdapter = client.app.state.telecom["media_gateway"]
    _open_gate(client)
    assert client.patch("/api/v1/settings", json={"values": {"gateway.enabled": True}}).status_code == 200
    _c, call_id = _live_call(client)

    path = FakePath(["yes this is Rahul", "yes go ahead", "we use excel", ("कीमत कितनी है", "interrupt"), "demo please", "kal shaam paanch baje", "ok thank you"])
    adapter.call_audio_path = lambda _cid: path  # the route yields a verified path (gate already satisfied above)
    tts = FakeTTS()
    client.app.state.autonomy.components = lambda _s: (FakeSTT(path), tts, {"en": "en-voice", "hi": "hi-voice"})
    client.app.state.autonomy.sleep = lambda _s: None

    r = client.post(f"/api/v1/calls/{call_id}/autonomy/start", json={"language": "en", "use_llm": False})
    assert r.status_code == 200, r.text
    s = client.app.state.autonomy.active
    assert s.wait(20), s.to_dict()
    assert s.status == "finished", s.to_dict()
    assert s.path.name == "media-gateway"
    assert s.interruptions >= 1 and "hi" in s.languages  # barge-in and language switch over the route
    said = " ".join(t for t, _, _ in tts.lines)
    assert "automated AI assistant" in said and "₹1,999" in said  # disclosure + approved price only
    assert any(v == "hi-voice" for _, v, _ in tts.lines)
    d = client.get(f"/api/v1/calls/{call_id}").json()
    prospect = [t for t in d["transcript"] if t["speaker"] == "prospect"]
    assert len(prospect) >= 5 and all(t["source"] == "stt" for t in prospect)
