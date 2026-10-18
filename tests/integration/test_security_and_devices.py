import json

import pytest
from sellagent_protocol import CallState, CallStateEvent, DeviceCapabilities, Envelope, Heartbeat, MessageType
from starlette.websockets import WebSocketDisconnect

from tests.conftest import LOCAL_TOKEN, make_contact, open_hours

pytestmark = pytest.mark.automated

PAIR = {"device_name": "Rahul S25", "device_model": "SM-S931B", "android_version": "15", "app_version": "0.1.0", "device_public_id": "pub-device-0001", "capabilities": {"can_place_calls": True, "reports_call_state": True, "remote_audio_capture_verified": True, "audio_injection_verified": True}}


def test_unauthenticated_requests_rejected(anon):
    assert anon.get("/api/v1/health/ping").status_code == 200
    for path in ("/api/v1/contacts", "/api/v1/settings", "/api/v1/devices", "/api/v1/audit", "/api/v1/backup"):
        assert anon.get(path).status_code == 401, path
    assert anon.get("/api/v1/contacts", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert anon.get("/api/v1/devices/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    with pytest.raises(WebSocketDisconnect):
        with anon.websocket_connect("/api/v1/ws/desktop?token=wrong"):
            pass
    with pytest.raises(WebSocketDisconnect):
        with anon.websocket_connect("/api/v1/ws/device?token=wrong"):
            pass


def _pair(client):
    w = client.post("/api/v1/devices/pairing/open").json()
    assert w["pairing_code"] and w["tls_fingerprint_sha256"] and len(w["tls_fingerprint_sha256"].split(":")) == 32
    r = client.post("/api/v1/devices/pair", json={**PAIR, "pairing_code": w["pairing_code"]}).json()
    assert r["status"] == "pending"
    assert client.get("/api/v1/devices/pair/result", params={"device_public_id": PAIR["device_public_id"]}).json()["status"] == "pending"
    st = client.get("/api/v1/devices/pairing/status").json()
    assert st["pending"]["device_model"] == "SM-S931B"
    d = client.post("/api/v1/devices/pairing/decide", json={"approve": True}).json()
    assert d["approved"]
    res = client.get("/api/v1/devices/pair/result", params={"device_public_id": PAIR["device_public_id"]}).json()
    assert res["status"] == "approved" and res["device_token"] and res["device_id"] == d["device_id"]
    # token is one-time: a second poll never returns it again
    assert client.get("/api/v1/devices/pair/result", params={"device_public_id": PAIR["device_public_id"]}).json()["status"] in ("expired", "unknown")
    return d["device_id"], res["device_token"]


def test_pairing_wrong_code_and_rejection(client):
    client.post("/api/v1/devices/pairing/open")
    assert client.post("/api/v1/devices/pair", json={**PAIR, "pairing_code": "AAAA-BBBB"}).json()["status"] == "invalid"
    assert client.post("/api/v1/devices/pairing/decide", json={"approve": True}).status_code == 404
    w = client.post("/api/v1/devices/pairing/open").json()
    client.post("/api/v1/devices/pair", json={**PAIR, "pairing_code": w["pairing_code"]})
    assert client.post("/api/v1/devices/pairing/decide", json={"approve": False}).json()["approved"] is False
    assert client.get("/api/v1/devices").json() == []


def test_pair_authenticate_revoke(client):
    device_id, token = _pair(client)
    me = client.get("/api/v1/devices/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["id"] == device_id and me["status"] == "approved"
    # capabilities that claim verified audio are stripped at pairing time
    assert me["capabilities"].get("remote_audio_capture_verified") is None and me["capabilities"]["can_place_calls"] is True
    client.post(f"/api/v1/devices/{device_id}/revoke")
    assert client.get("/api/v1/devices/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.delete(f"/api/v1/devices/{device_id}").status_code == 200


def test_device_websocket_heartbeat_dedupe_and_call_state(client):
    open_hours(client)
    device_id, token = _pair(client)
    c = make_contact(client)
    with client.websocket_connect(f"/api/v1/ws/desktop?token={LOCAL_TOKEN}") as desk:
        with client.websocket_connect("/api/v1/ws/device", headers={"Authorization": f"Bearer {token}"}) as dev:
            desk.receive_text()  # device-connected heartbeat broadcast
            hb = Envelope.of(MessageType.HEARTBEAT, Heartbeat(device_id=device_id, battery_percent=80, network="wifi", capabilities=DeviceCapabilities(can_place_calls=True, reports_call_state=True)))
            dev.send_text(hb.model_dump_json())
            ack = json.loads(dev.receive_text())
            assert ack["type"] == "session.heartbeat_ack" and ack["in_reply_to"] == hb.message_id and ack["payload"]["emergency_stop_active"] is False
            assert json.loads(desk.receive_text())["type"] == "session.heartbeat"
            # duplicate message id -> plain ack, not reprocessed
            dev.send_text(hb.model_dump_json())
            assert json.loads(dev.receive_text())["type"] == "ack"
            # malformed message -> error, connection stays open
            dev.send_text('{"type":"call.state","payload":{"bogus":1}}')
            assert json.loads(dev.receive_text())["type"] == "error"
            assert client.get("/api/v1/devices/connected").json()["connected"] == [device_id]
            # dispatch a call over the android route; device acks the call.request
            job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"], "route": "android_companion"}).json()
            assert job["status"] == "pending", job["eligibility_result"]
            import threading

            result: dict = {}

            def _dispatch() -> None:
                result["resp"] = client.post(f"/api/v1/call-jobs/{job['id']}/dispatch")

            th = threading.Thread(target=_dispatch)
            th.start()
            req = json.loads(dev.receive_text())
            assert req["type"] == "call.request" and req["payload"]["e164_number"] == "+919876543210" and req["payload"]["mode"] == "human_assisted"
            dev.send_text(Envelope(type=MessageType.ACK, payload={"message_id": req["message_id"]}, in_reply_to=req["message_id"]).model_dump_json())
            th.join(10)
            assert result["resp"].status_code == 200, result["resp"].text
            call_id = result["resp"].json()["call_id"]
            for state in (CallState.DIALING, CallState.ACTIVE):
                ev = Envelope.of(MessageType.CALL_STATE, CallStateEvent(call_job_id=job["id"], state=state, source="in_call_service"))
                dev.send_text(ev.model_dump_json())
                assert json.loads(dev.receive_text())["type"] == "ack"
            detail = client.get(f"/api/v1/calls/{call_id}").json()
            assert detail["call"]["conversation_state"] == "connected" and detail["job"]["status"] == "in_progress"
            assert [e["event_type"] for e in detail["events"]][-2:] == ["device.dialing", "device.active"]
            # emergency stop from desktop reaches the device
            client.post("/api/v1/call-jobs/emergency-stop", json={"reason": "test"})
            assert json.loads(dev.receive_text())["type"] == "safety.emergency_stop"
            assert client.get(f"/api/v1/call-jobs/{job['id']}").json()["status"] == "cancelled"


def test_audio_tests_release_gate(client):
    gate = client.get("/api/v1/settings/release-gate").json()
    assert gate["allowed"] is False
    assert client.patch("/api/v1/settings", json={"values": {"calling.autonomous_enabled": True}}).status_code == 400
    plan = client.get("/api/v1/audio-tests/plan").json()
    assert len(plan["steps"]) == 16
    # simulated passes never open the gate
    for direction in ("inbound", "outbound"):
        r = client.post("/api/v1/audio-tests", json={"test_id": "AFT-SIM", "step": "remote_speech_capture", "direction": direction, "status": "pass", "kind": "simulated"}).json()
        client.post(f"/api/v1/audio-tests/{r['id']}/confirm")
    assert client.get("/api/v1/settings/release-gate").json()["allowed"] is False
    # real-device inbound pass alone is not enough
    r1 = client.post("/api/v1/audio-tests", json={"test_id": "AFT-20261018-01", "step": "remote_speech_capture", "direction": "inbound", "status": "pass", "kind": "real_device", "phone_model": "SM-S931B"}).json()
    client.post(f"/api/v1/audio-tests/{r1['id']}/confirm")
    assert client.get("/api/v1/settings/release-gate").json()["allowed"] is False
    r2 = client.post("/api/v1/audio-tests", json={"test_id": "AFT-20261018-01", "step": "generated_speech_transmission", "direction": "outbound", "status": "pass", "kind": "real_device"}).json()
    assert client.get("/api/v1/settings/release-gate").json()["allowed"] is False  # not yet operator-confirmed
    client.post(f"/api/v1/audio-tests/{r2['id']}/confirm")
    g = client.get("/api/v1/settings/release-gate").json()
    assert g["allowed"] is True and g["setting"] is True and g["evidence"]["inbound"] == ["AFT-20261018-01"]
    assert client.patch("/api/v1/settings", json={"values": {"calling.autonomous_enabled": True}}).status_code == 200
    # deleting evidence closes the gate and switches autonomous off again
    client.delete(f"/api/v1/audio-tests/{r2['id']}")
    vals = client.get("/api/v1/settings").json()["values"]
    assert vals["release_gate.autonomous_calling_allowed"] is False and vals["calling.autonomous_enabled"] is False
    rep = client.get("/api/v1/audio-tests/report").json()
    assert rep["gate"]["allowed"] is False and any(s["latest"]["status"] == "not_tested" for s in rep["steps"])


def test_settings_validation_and_readonly(client):
    assert client.patch("/api/v1/settings", json={"values": {"release_gate.autonomous_calling_allowed": True}}).status_code == 400
    assert client.patch("/api/v1/settings", json={"values": {"calling.quiet_hours_start": "25:00"}}).status_code == 400
    assert client.patch("/api/v1/settings", json={"values": {"nope.key": 1}}).status_code == 400
    assert client.patch("/api/v1/settings", json={"values": {"calling.max_calls_per_day": "20"}}).json()["applied"]["calling.max_calls_per_day"] == 20
    audit = client.get("/api/v1/audit", params={"action": "settings.update"}).json()
    assert audit and audit[0]["entity_id"] == "calling.max_calls_per_day"


def test_health_reports_wal_fk_fts(client):
    h = client.get("/api/v1/health").json()
    assert h["ok"] and h["database"]["journal_mode"] == "wal" and h["database"]["foreign_keys"] and h["database"]["fts5"] and h["database"]["up_to_date"]
    assert h["bind"]["host"] == "127.0.0.1" and h["lan"]["enabled"] is False


def test_audit_never_stores_tokens(client):
    _pair(client)
    for e in client.get("/api/v1/audit").json():
        blob = json.dumps(e)
        assert "device_token" not in blob or "[REDACTED]" in blob


def test_local_token_rotation(client, settings):
    new = client.post("/api/v1/auth/rotate-local-token").json()["token"]
    assert client.get("/api/v1/contacts").status_code == 401
    assert client.get("/api/v1/contacts", headers={"Authorization": f"Bearer {new}"}).status_code == 200
    from sellagent_backend.security.secret_store import read_secret_file

    assert read_secret_file(settings.local_token_path) == new
