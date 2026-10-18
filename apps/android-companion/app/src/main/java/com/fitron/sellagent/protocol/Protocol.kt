// SELL AGENT wire protocol v1 - Kotlin mirror of packages/shared-protocol/sellagent_protocol/messages.py.
// This file is copied byte-for-byte into both Android apps (apps/*/app/src/main/java/com/fitron/sellagent/protocol/).
// Field names are pinned with @SerialName so that the JSON matches the Python/pydantic models exactly.
package com.fitron.sellagent.protocol

import java.time.Instant
import java.time.OffsetDateTime
import java.util.UUID
import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.serializer

const val PROTOCOL_VERSION: String = "1.0"

/** Message type identifiers (values of the Python `MessageType` enum). */
object MessageType {
    const val PAIRING_REQUEST = "pairing.request"
    const val PAIRING_RESPONSE = "pairing.response"
    const val PAIRING_COMPLETE = "pairing.complete"
    const val HEARTBEAT = "session.heartbeat"
    const val HEARTBEAT_ACK = "session.heartbeat_ack"
    const val RECONNECT_REQUEST = "session.reconnect"
    const val RECONNECT_RESPONSE = "session.reconnect_ack"
    const val CAPABILITIES = "session.capabilities"
    const val CALL_REQUEST = "call.request"
    const val CALL_STATE = "call.state"
    const val CALL_CANCEL = "call.cancel"
    const val AUDIO_TEST_START = "audio_test.start"
    const val AUDIO_TEST_EVENT = "audio_test.event"
    const val AUDIO_TEST_RESULT = "audio_test.result"
    const val EMERGENCY_STOP = "safety.emergency_stop"
    const val EMERGENCY_STOP_ACK = "safety.emergency_stop_ack"
    const val ERROR = "error"
    const val ACK = "ack"

    /** Inbound message types for which the backend awaits an `ack` (or `error`) envelope with `in_reply_to`. */
    val ACK_EXPECTED: Set<String> = setOf(CALL_REQUEST)
}

/** Values of the Python `CallState` enum. */
object CallState {
    const val REQUESTED = "requested"
    const val DIALING = "dialing"
    const val RINGING = "ringing"
    const val ACTIVE = "active"
    const val HOLDING = "holding"
    const val DISCONNECTED = "disconnected"
    const val FAILED = "failed"
    const val REJECTED = "rejected"
    const val OFFHOOK = "offhook"
    const val IDLE = "idle"
    const val UNKNOWN = "unknown"
}

/** Values of the Python `AudioRoute` enum. */
object AudioRoute {
    const val EARPIECE = "earpiece"
    const val SPEAKER = "speaker"
    const val BLUETOOTH = "bluetooth"
    const val WIRED_HEADSET = "wired_headset"
    const val UNKNOWN = "unknown"
}

/** Values of the Python `AudioDirection` enum. */
object AudioDirection {
    const val INBOUND = "inbound"
    const val OUTBOUND = "outbound"
    const val BOTH = "both"
    const val NONE = "none"
}

/** Values of `AudioTestResult.status`. */
object TestStatus {
    const val PASS = "pass"
    const val FAIL = "fail"
    const val BLOCKED = "blocked"
    const val NOT_TESTED = "not_tested"
}

/** Values of `CallStateEvent.source`. */
object CallStateSource {
    const val IN_CALL_SERVICE = "in_call_service"
    const val TELEPHONY_CALLBACK = "telephony_callback"
    const val APP = "app"
}

/** Values of `CallRequest.mode`. */
object CallMode {
    const val HUMAN_ASSISTED = "human_assisted"
    const val AUTONOMOUS = "autonomous"
}

/** Values of `Heartbeat.network`. */
object NetworkKind {
    const val WIFI = "wifi"
    const val CELLULAR = "cellular"
    const val NONE = "none"
    const val UNKNOWN = "unknown"
}

/**
 * Capabilities positively reported by the Android app. Everything defaults to false; the app sets a flag only
 * from a verified runtime fact (granted permission, held role, bound service). `remote_audio_capture_verified`
 * and `audio_injection_verified` are NEVER set to true by the apps: the backend derives them from
 * operator-confirmed real-device audio test records.
 */
@Serializable
data class DeviceCapabilities(
    @SerialName("can_place_calls") val canPlaceCalls: Boolean = false,
    @SerialName("reports_call_state") val reportsCallState: Boolean = false,
    @SerialName("is_default_dialer") val isDefaultDialer: Boolean = false,
    @SerialName("can_control_audio_route") val canControlAudioRoute: Boolean = false,
    @SerialName("can_end_calls") val canEndCalls: Boolean = false,
    @SerialName("supports_foreground_service") val supportsForegroundService: Boolean = false,
    @SerialName("remote_audio_capture_verified") val remoteAudioCaptureVerified: Boolean = false,
    @SerialName("audio_injection_verified") val audioInjectionVerified: Boolean = false,
    @SerialName("wifi_calling_active") val wifiCallingActive: Boolean? = null,
    @SerialName("android_sdk_int") val androidSdkInt: Int? = null,
    @SerialName("device_model") val deviceModel: String? = null,
    @SerialName("app_version") val appVersion: String? = null,
    @SerialName("notes") val notes: String? = null,
)

/** HTTP body of POST /api/v1/devices/pair. */
@Serializable
data class PairingRequest(
    @SerialName("pairing_code") val pairingCode: String,
    @SerialName("device_name") val deviceName: String,
    @SerialName("device_model") val deviceModel: String,
    @SerialName("android_version") val androidVersion: String,
    @SerialName("app_version") val appVersion: String,
    @SerialName("device_public_id") val devicePublicId: String,
    @SerialName("capabilities") val capabilities: DeviceCapabilities = DeviceCapabilities(),
)

/** Reply of POST /api/v1/devices/pair (`status` is pending | approved | rejected | expired | invalid). */
@Serializable
data class PairingResponse(
    @SerialName("status") val status: String,
    @SerialName("device_id") val deviceId: String? = null,
    @SerialName("message") val message: String? = null,
    @SerialName("protocol_version") val protocolVersion: String? = null,
)

/** Reply of GET /api/v1/devices/pair/result. The token is present exactly once, when status == approved. */
@Serializable
data class PairingResult(
    @SerialName("status") val status: String,
    @SerialName("device_id") val deviceId: String? = null,
    @SerialName("device_token") val deviceToken: String? = null,
    @SerialName("backend_name") val backendName: String? = null,
    @SerialName("protocol_version") val protocolVersion: String? = null,
    @SerialName("ws_path") val wsPath: String? = null,
)

@Serializable
data class PairingComplete(
    @SerialName("device_id") val deviceId: String,
    @SerialName("device_token") val deviceToken: String,
    @SerialName("token_expires_at") val tokenExpiresAt: String? = null,
    @SerialName("backend_name") val backendName: String,
    @SerialName("protocol_version") val protocolVersion: String = PROTOCOL_VERSION,
)

@Serializable
data class Heartbeat(
    @SerialName("device_id") val deviceId: String,
    @SerialName("battery_percent") val batteryPercent: Int? = null,
    @SerialName("network") val network: String = NetworkKind.UNKNOWN,
    @SerialName("wifi_calling_active") val wifiCallingActive: Boolean? = null,
    @SerialName("in_call") val inCall: Boolean = false,
    @SerialName("capabilities") val capabilities: DeviceCapabilities? = null,
)

@Serializable
data class HeartbeatAck(
    @SerialName("server_time") val serverTime: String? = null,
    @SerialName("emergency_stop_active") val emergencyStopActive: Boolean = false,
)

@Serializable
data class ReconnectRequest(
    @SerialName("device_id") val deviceId: String,
    @SerialName("last_received_message_id") val lastReceivedMessageId: String? = null,
    @SerialName("pending_events") val pendingEvents: Int = 0,
)

@Serializable
data class ReconnectResponse(
    @SerialName("accepted") val accepted: Boolean,
    @SerialName("emergency_stop_active") val emergencyStopActive: Boolean = false,
    @SerialName("resume_from_message_id") val resumeFromMessageId: String? = null,
    @SerialName("message") val message: String? = null,
)

@Serializable
data class CallRequest(
    @SerialName("call_job_id") val callJobId: String,
    @SerialName("e164_number") val e164Number: String,
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("mode") val mode: String = CallMode.HUMAN_ASSISTED,
    @SerialName("authorization_token") val authorizationToken: String,
    @SerialName("requested_route") val requestedRoute: String? = null,
    @SerialName("language") val language: String = "auto",
    @SerialName("expires_at") val expiresAt: String,
)

@Serializable
data class CallStateEvent(
    @SerialName("call_job_id") val callJobId: String,
    @SerialName("state") val state: String,
    @SerialName("occurred_at") val occurredAt: String = nowIso(),
    @SerialName("audio_route") val audioRoute: String? = null,
    @SerialName("disconnect_cause") val disconnectCause: String? = null,
    @SerialName("source") val source: String = CallStateSource.APP,
    @SerialName("detail") val detail: String? = null,
)

@Serializable
data class CancelRequest(
    @SerialName("call_job_id") val callJobId: String,
    @SerialName("reason") val reason: String = "operator_cancel",
)

@Serializable
data class AudioTestEvent(
    @SerialName("test_id") val testId: String,
    @SerialName("step") val step: String,
    @SerialName("direction") val direction: String = AudioDirection.NONE,
    @SerialName("route") val route: String? = null,
    @SerialName("level_dbfs") val levelDbfs: Double? = null,
    @SerialName("latency_ms") val latencyMs: Double? = null,
    @SerialName("message") val message: String? = null,
    @SerialName("occurred_at") val occurredAt: String = nowIso(),
)

@Serializable
data class AudioTestResult(
    @SerialName("test_id") val testId: String,
    @SerialName("step") val step: String,
    @SerialName("direction") val direction: String,
    @SerialName("status") val status: String,
    @SerialName("route") val route: String? = null,
    @SerialName("api_used") val apiUsed: String? = null,
    @SerialName("error_message") val errorMessage: String? = null,
    @SerialName("metrics") val metrics: Map<String, Double> = emptyMap(),
    @SerialName("evidence") val evidence: Map<String, String> = emptyMap(),
    @SerialName("occurred_at") val occurredAt: String = nowIso(),
)

@Serializable
data class EmergencyStop(
    @SerialName("reason") val reason: String = "operator_emergency_stop",
    @SerialName("issued_by") val issuedBy: String = "windows",
)

@Serializable
data class ErrorEvent(
    @SerialName("code") val code: String,
    @SerialName("message") val message: String,
    @SerialName("retryable") val retryable: Boolean = false,
    @SerialName("detail") val detail: JsonObject? = null,
)

@Serializable
data class Ack(
    @SerialName("message_id") val messageId: String,
)

/** Transport envelope. `payload` is kept as a raw JsonObject and decoded by type. */
@Serializable
data class Envelope(
    @SerialName("protocol_version") val protocolVersion: String = PROTOCOL_VERSION,
    @SerialName("type") val type: String,
    @SerialName("message_id") val messageId: String = newMessageId(),
    @SerialName("sent_at") val sentAt: String = nowIso(),
    @SerialName("in_reply_to") val inReplyTo: String? = null,
    @SerialName("payload") val payload: JsonObject = JsonObject(emptyMap()),
) {
    fun toJson(): String = ProtocolJson.encodeToString(this)

    /** True when the major version matches ours (the backend applies the same rule). */
    val isSupportedVersion: Boolean
        get() = protocolVersion.substringBefore('.') == PROTOCOL_VERSION.substringBefore('.')

    companion object {
        fun parse(raw: String): Envelope = ProtocolJson.decodeFromString(serializer(), raw)

        fun <T> of(type: String, payload: T, payloadSerializer: KSerializer<T>, inReplyTo: String? = null): Envelope =
            Envelope(
                type = type,
                inReplyTo = inReplyTo,
                payload = ProtocolJson.encodeToJsonElement(payloadSerializer, payload).jsonObject,
            )

        fun ack(inReplyTo: String): Envelope = of(MessageType.ACK, Ack(inReplyTo), Ack.serializer(), inReplyTo)

        fun error(code: String, message: String, inReplyTo: String? = null, retryable: Boolean = false): Envelope =
            of(MessageType.ERROR, ErrorEvent(code = code, message = message.take(1000), retryable = retryable), ErrorEvent.serializer(), inReplyTo)
    }
}

/** Decode the payload of an envelope as [T]. Throws on mismatch; callers wrap in runCatching. */
inline fun <reified T> Envelope.payloadAs(): T = ProtocolJson.decodeFromJsonElement(serializer<T>(), payload)

/** Shared Json configuration: unknown keys are ignored, nulls are omitted, defaults are written. */
val ProtocolJson: Json = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    encodeDefaults = true
    isLenient = false
}

fun newMessageId(): String = UUID.randomUUID().toString().replace("-", "")

fun nowIso(): String = Instant.now().toString()

/** Parses pydantic datetimes ("...Z" or "...+00:00"). Returns null when unparsable. */
fun parseIsoInstant(value: String?): Instant? {
    if (value.isNullOrBlank()) return null
    return runCatching { OffsetDateTime.parse(value).toInstant() }
        .recoverCatching { Instant.parse(value) }
        .getOrNull()
}
