"""Protocol v1 message definitions.

Design rules
------------
* Every message travels inside an :class:`Envelope` carrying ``protocol_version``,
  a unique ``message_id`` (for de-duplication and acknowledgement), a UTC
  ``sent_at`` timestamp and an optional ``in_reply_to``.
* Payloads are strict (``extra="forbid"``) so that malformed or unexpected data
  is rejected rather than silently accepted.
* Capability flags default to *False*. A device must positively report a
  capability; the backend never assumes it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROTOCOL_VERSION = "1.0"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid.uuid4().hex


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MessageType(StrEnum):
    # Pairing
    PAIRING_REQUEST = "pairing.request"
    PAIRING_RESPONSE = "pairing.response"
    PAIRING_COMPLETE = "pairing.complete"
    # Session
    HEARTBEAT = "session.heartbeat"
    HEARTBEAT_ACK = "session.heartbeat_ack"
    RECONNECT_REQUEST = "session.reconnect"
    RECONNECT_RESPONSE = "session.reconnect_ack"
    CAPABILITIES = "session.capabilities"
    # Calls
    CALL_REQUEST = "call.request"
    CALL_STATE = "call.state"
    CALL_CANCEL = "call.cancel"
    # Audio diagnostics
    AUDIO_TEST_START = "audio_test.start"
    AUDIO_TEST_EVENT = "audio_test.event"
    AUDIO_TEST_RESULT = "audio_test.result"
    # Safety
    EMERGENCY_STOP = "safety.emergency_stop"
    EMERGENCY_STOP_ACK = "safety.emergency_stop_ack"
    # Errors / acks
    ERROR = "error"
    ACK = "ack"


class CallState(StrEnum):
    """Call states as reported by the Android companion.

    These map onto documented ``android.telecom.Call`` states
    (``STATE_DIALING``, ``STATE_RINGING``, ``STATE_ACTIVE``, ``STATE_HOLDING``,
    ``STATE_DISCONNECTED``) and ``TelephonyCallback.CallStateListener`` states
    (``CALL_STATE_IDLE``, ``CALL_STATE_RINGING``, ``CALL_STATE_OFFHOOK``).
    ``UNKNOWN`` is reported when the app can only observe coarse state.
    """

    REQUESTED = "requested"
    DIALING = "dialing"
    RINGING = "ringing"
    ACTIVE = "active"
    HOLDING = "holding"
    DISCONNECTED = "disconnected"
    FAILED = "failed"
    REJECTED = "rejected"  # app refused to dial (permission/eligibility/emergency stop)
    OFFHOOK = "offhook"  # coarse state only (TelephonyCallback)
    IDLE = "idle"
    UNKNOWN = "unknown"


class AudioRoute(StrEnum):
    EARPIECE = "earpiece"
    SPEAKER = "speaker"
    BLUETOOTH = "bluetooth"
    WIRED_HEADSET = "wired_headset"
    UNKNOWN = "unknown"


class AudioDirection(StrEnum):
    INBOUND = "inbound"  # remote party -> app (capture)
    OUTBOUND = "outbound"  # app -> remote party (injection)
    BOTH = "both"
    NONE = "none"


class DeviceCapabilities(StrictModel):
    """Capabilities positively reported by the Android app.

    Everything defaults to False. The backend's release gate for autonomous
    calling requires ``remote_audio_capture_verified`` and
    ``audio_injection_verified`` to be True *and* backed by a passing real-device
    audio test record. The companion app only sets them from stored diagnostic
    results, never from assumptions.
    """

    can_place_calls: bool = False
    reports_call_state: bool = False
    is_default_dialer: bool = False
    can_control_audio_route: bool = False
    can_end_calls: bool = False
    supports_foreground_service: bool = False
    remote_audio_capture_verified: bool = False
    audio_injection_verified: bool = False
    wifi_calling_active: bool | None = None
    android_sdk_int: int | None = None
    device_model: str | None = None
    app_version: str | None = None
    notes: str | None = None


class PairingRequest(StrictModel):
    """Sent by the Android app after the user types the code shown on Windows."""

    pairing_code: Annotated[str, Field(min_length=6, max_length=12, pattern=r"^[A-Z0-9-]+$")]
    device_name: Annotated[str, Field(min_length=1, max_length=80)]
    device_model: Annotated[str, Field(min_length=1, max_length=80)]
    android_version: Annotated[str, Field(min_length=1, max_length=40)]
    app_version: Annotated[str, Field(min_length=1, max_length=40)]
    device_public_id: Annotated[str, Field(min_length=8, max_length=128)]
    capabilities: DeviceCapabilities = Field(default_factory=DeviceCapabilities)


class PairingResponse(StrictModel):
    """Backend reply. ``status`` is ``pending`` until the Windows user approves."""

    status: Literal["pending", "approved", "rejected", "expired", "invalid"]
    device_id: str | None = None
    message: str | None = None


class PairingComplete(StrictModel):
    """Sent once the Windows user approves. Token is shown exactly once."""

    device_id: str
    device_token: str
    token_expires_at: datetime | None = None
    backend_name: str
    protocol_version: str = PROTOCOL_VERSION


class Heartbeat(StrictModel):
    device_id: str
    battery_percent: int | None = Field(default=None, ge=0, le=100)
    network: Literal["wifi", "cellular", "none", "unknown"] = "unknown"
    wifi_calling_active: bool | None = None
    in_call: bool = False
    capabilities: DeviceCapabilities | None = None


class HeartbeatAck(StrictModel):
    server_time: datetime = Field(default_factory=_utcnow)
    emergency_stop_active: bool = False


class ReconnectRequest(StrictModel):
    device_id: str
    last_received_message_id: str | None = None
    pending_events: int = 0


class ReconnectResponse(StrictModel):
    accepted: bool
    emergency_stop_active: bool = False
    resume_from_message_id: str | None = None
    message: str | None = None


class CallRequest(StrictModel):
    """Backend -> device: place a call. The device must verify ``authorization_token``
    matches the current session and refuse when emergency stop is active."""

    call_job_id: str
    e164_number: Annotated[str, Field(pattern=r"^\+[1-9]\d{6,14}$")]
    display_name: str | None = None
    mode: Literal["human_assisted", "autonomous"] = "human_assisted"
    authorization_token: Annotated[str, Field(min_length=16, max_length=256)]
    requested_route: AudioRoute | None = None
    language: Literal["hi", "en", "auto"] = "auto"
    expires_at: datetime


class CallStateEvent(StrictModel):
    call_job_id: str
    state: CallState
    occurred_at: datetime = Field(default_factory=_utcnow)
    audio_route: AudioRoute | None = None
    disconnect_cause: str | None = None
    source: Literal["in_call_service", "telephony_callback", "app"] = "app"
    detail: str | None = None


class CancelRequest(StrictModel):
    call_job_id: str
    reason: Annotated[str, Field(max_length=200)] = "operator_cancel"


class AudioTestEvent(StrictModel):
    test_id: str
    step: str
    direction: AudioDirection = AudioDirection.NONE
    route: AudioRoute | None = None
    level_dbfs: float | None = None
    latency_ms: float | None = None
    message: str | None = None
    occurred_at: datetime = Field(default_factory=_utcnow)


class AudioTestResult(StrictModel):
    """Final outcome of one diagnostic step, reported by the device.

    ``status`` is never inferred by the backend; the device sets it from what
    it actually observed, and the operator confirms it on Windows.
    """

    test_id: str
    step: str
    direction: AudioDirection
    status: Literal["pass", "fail", "blocked", "not_tested"]
    route: AudioRoute | None = None
    api_used: str | None = None
    error_message: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    evidence: dict[str, str] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=_utcnow)


class EmergencyStop(StrictModel):
    reason: Annotated[str, Field(max_length=200)] = "operator_emergency_stop"
    issued_by: Literal["windows", "android"] = "windows"


class ErrorEvent(StrictModel):
    code: Annotated[str, Field(max_length=64)]
    message: Annotated[str, Field(max_length=1000)]
    retryable: bool = False
    detail: dict[str, Any] | None = None


class Ack(StrictModel):
    message_id: str


_PAYLOADS: dict[MessageType, type[BaseModel]] = {
    MessageType.PAIRING_REQUEST: PairingRequest,
    MessageType.PAIRING_RESPONSE: PairingResponse,
    MessageType.PAIRING_COMPLETE: PairingComplete,
    MessageType.HEARTBEAT: Heartbeat,
    MessageType.HEARTBEAT_ACK: HeartbeatAck,
    MessageType.RECONNECT_REQUEST: ReconnectRequest,
    MessageType.RECONNECT_RESPONSE: ReconnectResponse,
    MessageType.CAPABILITIES: DeviceCapabilities,
    MessageType.CALL_REQUEST: CallRequest,
    MessageType.CALL_STATE: CallStateEvent,
    MessageType.CALL_CANCEL: CancelRequest,
    MessageType.AUDIO_TEST_START: AudioTestEvent,
    MessageType.AUDIO_TEST_EVENT: AudioTestEvent,
    MessageType.AUDIO_TEST_RESULT: AudioTestResult,
    MessageType.EMERGENCY_STOP: EmergencyStop,
    MessageType.EMERGENCY_STOP_ACK: Ack,
    MessageType.ERROR: ErrorEvent,
    MessageType.ACK: Ack,
}


def payload_model_for(message_type: MessageType) -> type[BaseModel]:
    return _PAYLOADS[message_type]


class Envelope(StrictModel):
    protocol_version: str = PROTOCOL_VERSION
    type: MessageType
    message_id: str = Field(default_factory=_new_id)
    sent_at: datetime = Field(default_factory=_utcnow)
    in_reply_to: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("protocol_version")
    @classmethod
    def _check_version(cls, v: str) -> str:
        major = v.split(".")[0]
        if major != PROTOCOL_VERSION.split(".")[0]:
            raise ValueError(f"unsupported protocol major version {v!r}; expected {PROTOCOL_VERSION}")
        return v

    def typed_payload(self) -> BaseModel:
        return payload_model_for(self.type).model_validate(self.payload)

    @classmethod
    def wrap(cls, payload: BaseModel, *, in_reply_to: str | None = None) -> Envelope:
        for mtype, model in _PAYLOADS.items():
            if type(payload) is model and mtype not in (MessageType.AUDIO_TEST_START, MessageType.EMERGENCY_STOP_ACK):
                return cls(type=mtype, payload=payload.model_dump(mode="json"), in_reply_to=in_reply_to)
        raise TypeError(f"no message type registered for payload {type(payload).__name__}")

    @classmethod
    def of(cls, mtype: MessageType, payload: BaseModel, *, in_reply_to: str | None = None) -> Envelope:
        expected = _PAYLOADS[mtype]
        if not isinstance(payload, expected):
            raise TypeError(f"{mtype} expects {expected.__name__}, got {type(payload).__name__}")
        return cls(type=mtype, payload=payload.model_dump(mode="json"), in_reply_to=in_reply_to)


def parse_envelope(raw: str | bytes | dict[str, Any]) -> tuple[Envelope, BaseModel]:
    """Parse and validate a wire message. Raises ``pydantic.ValidationError``."""
    env = Envelope.model_validate_json(raw) if isinstance(raw, str | bytes) else Envelope.model_validate(raw)
    return env, env.typed_payload()


def export_json_schemas() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {"Envelope": Envelope.model_json_schema()}
    for mtype, model in _PAYLOADS.items():
        out[mtype.value] = model.model_json_schema()
    return out
