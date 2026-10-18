"""Asterisk AudioSocket transport/server for the USB-modem/SIP media gateway. Exercises the real wire protocol
over a loopback TCP socket (Asterisk is simulated as the client). No modem, no Asterisk, no network beyond
loopback - it proves the framing, the UUID->call binding and the fail-closed refusal of unknown calls."""

from __future__ import annotations

import socket
import struct
import threading
import time
import uuid

import pytest
from sellagent_backend.telecom.audiosocket import (
    FRAME_BYTES,
    TYPE_AUDIO,
    TYPE_HANGUP,
    TYPE_UUID,
    AudioSocketServer,
    AudioSocketTransport,
    read_frame,
)

pytestmark = pytest.mark.simulated
TONE = (b"\x11\x22") * (FRAME_BYTES // 2)


def _client_to(server: AudioSocketServer) -> socket.socket:
    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c.connect((server.host, server.bound_port))
    return c


def _send(conn: socket.socket, ftype: int, payload: bytes) -> None:
    conn.sendall(struct.pack(">BH", ftype, len(payload)) + payload)


def test_transport_frames_round_trip_over_a_socket():
    a, b = socket.socketpair()
    t = AudioSocketTransport(a)
    # AI -> Asterisk: send() emits a well-formed AUDIO frame
    t.send(TONE)
    ftype, payload = read_frame(b)
    assert ftype == TYPE_AUDIO and payload == TONE
    # wrong-size frames are dropped, never sent
    t.send(b"\x00" * 10)
    # Asterisk -> AI: the server feeds decoded frames; recv() hands them out, then None
    t.feed(TONE)
    assert t.recv() == TONE and t.recv() is None
    # close() tells the far end to hang up
    t.close()
    assert read_frame(b)[0] == TYPE_HANGUP and not t.is_connected()
    b.close()


def test_server_binds_known_call_and_bridges_audio():
    bound: dict[str, AudioSocketTransport] = {}
    call_id = uuid.uuid4().hex
    srv = AudioSocketServer(
        "127.0.0.1", 0,
        resolve=lambda u: call_id if u == call_id else None,
        bind=lambda cid, tr: bound.__setitem__(cid, tr),
        unbind=lambda cid: bound.pop(cid, None),
    )
    srv.start()
    try:
        conn = _client_to(srv)
        _send(conn, TYPE_UUID, bytes.fromhex(call_id))
        _send(conn, TYPE_AUDIO, TONE)
        for _ in range(50):
            if call_id in bound and bound[call_id].recv() is not None:
                break
            time.sleep(0.02)
        assert call_id in bound  # the call was bound to a transport
        # the AI side can write back out to Asterisk
        bound[call_id].send(TONE)
        assert read_frame(conn)[0] == TYPE_AUDIO
        conn.close()
        for _ in range(50):
            if call_id not in bound:
                break
            time.sleep(0.02)
        assert call_id not in bound  # hangup/EOF unbinds
    finally:
        srv.stop()


def test_server_refuses_unknown_uuid():
    bound: dict[str, AudioSocketTransport] = {}
    srv = AudioSocketServer(
        "127.0.0.1", 0,
        resolve=lambda _u: None,  # no call matches
        bind=lambda cid, tr: bound.__setitem__(cid, tr),
        unbind=lambda cid: bound.pop(cid, None),
    )
    srv.start()
    try:
        conn = _client_to(srv)
        _send(conn, TYPE_UUID, bytes.fromhex(uuid.uuid4().hex))
        time.sleep(0.2)
        assert bound == {}  # nothing bound; connection refused
        conn.close()
    finally:
        srv.stop()


def test_resolve_uuid_matches_live_call(client):
    from conftest import make_contact, open_hours

    gw = client.app.state.telecom["media_gateway"]
    client.patch("/api/v1/settings", json={"values": {"gateway.enabled": True}})
    open_hours(client)
    c = make_contact(client)
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"], "route": "media_gateway"}).json()
    call_id = client.post(f"/api/v1/call-jobs/{job['id']}/dispatch").json()["call_id"]
    assert gw.resolve_uuid(call_id) == call_id
    assert gw.resolve_uuid(uuid.uuid4().hex) is None  # unknown call
    assert gw.resolve_uuid("too-short") is None


# keep threading import referenced for readers scanning imports
_ = threading
