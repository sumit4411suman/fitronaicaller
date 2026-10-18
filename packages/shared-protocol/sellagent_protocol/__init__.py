"""SELL AGENT shared protocol.

Versioned message schemas exchanged between the Windows backend and the Android
companion / audio-diagnostic apps over an authenticated WebSocket.

The same schemas are exported to ``packages/shared-protocol/schema/*.json`` and
mirrored by Kotlin data classes in ``packages/shared-protocol/kotlin``.
"""

from sellagent_protocol.messages import (
    PROTOCOL_VERSION,
    AudioDirection,
    AudioRoute,
    AudioTestEvent,
    AudioTestResult,
    CallRequest,
    CallState,
    CallStateEvent,
    CancelRequest,
    DeviceCapabilities,
    EmergencyStop,
    Envelope,
    ErrorEvent,
    Event,
    Heartbeat,
    HeartbeatAck,
    MessageType,
    PairingComplete,
    PairingRequest,
    PairingResponse,
    ReconnectRequest,
    ReconnectResponse,
    parse_envelope,
    payload_model_for,
)

__all__ = [
    "PROTOCOL_VERSION",
    "AudioDirection",
    "AudioRoute",
    "AudioTestEvent",
    "AudioTestResult",
    "CallRequest",
    "CallState",
    "CallStateEvent",
    "CancelRequest",
    "DeviceCapabilities",
    "EmergencyStop",
    "Envelope",
    "ErrorEvent",
    "Event",
    "Heartbeat",
    "HeartbeatAck",
    "MessageType",
    "PairingComplete",
    "PairingRequest",
    "PairingResponse",
    "ReconnectRequest",
    "ReconnectResponse",
    "parse_envelope",
    "payload_model_for",
]
