import pytest
from pydantic import ValidationError
from sellagent_protocol import (
    PROTOCOL_VERSION,
    CallRequest,
    CallState,
    CallStateEvent,
    Envelope,
    Heartbeat,
    MessageType,
    parse_envelope,
)
from sellagent_protocol.messages import export_json_schemas

pytestmark = pytest.mark.automated


def test_roundtrip_heartbeat():
    env = Envelope.wrap(Heartbeat(device_id="dev1", battery_percent=77, network="wifi"))
    parsed, payload = parse_envelope(env.model_dump_json())
    assert parsed.type == MessageType.HEARTBEAT and isinstance(payload, Heartbeat) and payload.battery_percent == 77


def test_strict_payload_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        parse_envelope({"type": "session.heartbeat", "payload": {"device_id": "x", "bogus": 1}})


def test_rejects_other_major_version():
    with pytest.raises(ValidationError):
        Envelope(protocol_version="2.0", type=MessageType.ACK, payload={"message_id": "a"})
    assert Envelope(protocol_version="1.3", type=MessageType.ACK, payload={"message_id": "a"}).protocol_version == "1.3"


def test_call_request_requires_e164_and_token():
    from datetime import UTC, datetime, timedelta

    with pytest.raises(ValidationError):
        CallRequest(call_job_id="j", e164_number="98765", authorization_token="x" * 20, expires_at=datetime.now(UTC) + timedelta(minutes=1))
    with pytest.raises(ValidationError):
        CallRequest(call_job_id="j", e164_number="+919876543210", authorization_token="short", expires_at=datetime.now(UTC))


def test_capabilities_default_false():
    from sellagent_protocol import DeviceCapabilities

    c = DeviceCapabilities()
    assert not c.remote_audio_capture_verified and not c.audio_injection_verified and not c.can_place_calls


def test_call_state_event_and_schema_export():
    ev = CallStateEvent(call_job_id="j1", state=CallState.ACTIVE, source="in_call_service")
    env = Envelope.of(MessageType.CALL_STATE, ev)
    assert env.payload["state"] == "active"
    schemas = export_json_schemas()
    assert "call.state" in schemas and schemas["Envelope"]["properties"]["protocol_version"]["default"] == PROTOCOL_VERSION
