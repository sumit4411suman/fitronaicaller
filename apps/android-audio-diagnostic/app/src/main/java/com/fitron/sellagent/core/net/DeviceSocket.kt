package com.fitron.sellagent.core.net

import com.fitron.sellagent.core.log.AppLog
import com.fitron.sellagent.core.security.FingerprintTrust
import com.fitron.sellagent.core.security.Pairing
import com.fitron.sellagent.core.security.SecureStore
import com.fitron.sellagent.protocol.Ack
import com.fitron.sellagent.protocol.Envelope
import com.fitron.sellagent.protocol.ErrorEvent
import com.fitron.sellagent.protocol.EventPayload
import com.fitron.sellagent.protocol.Heartbeat
import com.fitron.sellagent.protocol.HeartbeatAck
import com.fitron.sellagent.protocol.MessageType
import com.fitron.sellagent.protocol.ReconnectRequest
import com.fitron.sellagent.protocol.ReconnectResponse
import com.fitron.sellagent.protocol.payloadAs
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import kotlin.math.min
import kotlin.random.Random
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

sealed class ConnectionState {
    data object Stopped : ConnectionState()
    data object Unpaired : ConnectionState()
    data object Connecting : ConnectionState()
    data class Connected(val backendName: String) : ConnectionState()
    data class Backoff(val retryInSeconds: Int, val reason: String) : ConnectionState()
}

/**
 * Persistent WebSocket session with the backend (wss://<pc>:8766/api/v1/ws/device).
 *
 *  - TLS: pinned to the fingerprint stored with the pairing (FingerprintTrust); bearer token in the Authorization header.
 *  - Reconnect: exponential backoff 1 s .. 60 s with jitter; `session.reconnect` (device_id, last_received_message_id,
 *    pending_events) is sent on every (re)connect, then unacknowledged envelopes are replayed from the file-backed outbox.
 *  - Inbound: de-duplicated by message_id (a repeated call.request is re-acked, not re-emitted);
 *    heartbeat_ack / reconnect_ack update the emergency-stop latch; everything else is exposed on [inbound].
 *  - Heartbeat every 20 s while connected.
 */
class DeviceSocket(
    private val store: SecureStore,
    private val outbox: OutboxQueue,
    private val scope: CoroutineScope,
    private val heartbeatProvider: () -> Heartbeat?,
) {
    private val _state = MutableStateFlow<ConnectionState>(ConnectionState.Stopped)
    val state: StateFlow<ConnectionState> = _state

    private val _inbound = MutableSharedFlow<Envelope>(extraBufferCapacity = 128, onBufferOverflow = BufferOverflow.SUSPEND)
    val inbound: SharedFlow<Envelope> = _inbound

    private val _emergencyStopActive = MutableStateFlow(store.emergencyStopLatched)
    val emergencyStopActive: StateFlow<Boolean> = _emergencyStopActive

    private val _pendingCount = MutableStateFlow(outbox.size())
    val pendingCount: StateFlow<Int> = _pendingCount

    private val _log = MutableStateFlow<List<String>>(emptyList())
    /** Short human-readable transport log (types and ids only; never payloads or tokens). */
    val log: StateFlow<List<String>> = _log

    private val _lastHeartbeatAckAt = MutableStateFlow<Long?>(null)
    val lastHeartbeatAckAt: StateFlow<Long?> = _lastHeartbeatAckAt

    private val _lastFailure = MutableStateFlow<String?>(null)
    /** Reason of the most recent connection failure (sanitized), shown by Troubleshooting. Cleared on connect. */
    val lastFailure: StateFlow<String?> = _lastFailure

    /** True when the last failure was a TLS certificate / pin mismatch. */
    val lastFailureIsCertificate: Boolean
        get() = _lastFailure.value?.let { f -> CERT_MARKERS.any { f.contains(it, ignoreCase = true) } } == true

    private val _lastEvent = MutableStateFlow<EventPayload?>(null)
    /** Last generic `event` notification from the backend (informational). */
    val lastEvent: StateFlow<EventPayload?> = _lastEvent

    @Volatile var lastReceivedMessageId: String? = null
        private set

    private var loopJob: Job? = null
    private var pairingWatch: Job? = null
    private var heartbeatJob: Job? = null
    @Volatile private var current: WebSocket? = null
    @Volatile private var connected = false
    private var closedSignal: CompletableDeferred<String>? = null
    private val seen = object : LinkedHashMap<String, Boolean>(512, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Boolean>?): Boolean = size > 2000
    }
    private val seenLock = Any()

    val isConnected: Boolean get() = connected

    fun start() {
        if (loopJob?.isActive == true) return
        loopJob = scope.launch { connectLoop() }
        if (pairingWatch == null) {
            pairingWatch = scope.launch {
                store.pairing.collect { p -> if (p == null) current?.cancel() }
            }
        }
    }

    fun stop() {
        loopJob?.cancel()
        loopJob = null
        heartbeatJob?.cancel()
        current?.close(1000, "app stopped")
        current = null
        connected = false
        _state.value = ConnectionState.Stopped
    }

    /** Drop the current socket; the loop reconnects immediately. */
    fun reconnectNow() {
        current?.cancel()
        closedSignal?.complete("manual reconnect")
    }

    /** Send an envelope. Durable envelopes are kept in the outbox until the backend acks them. */
    fun send(env: Envelope, durable: Boolean = true) {
        if (durable) {
            outbox.add(env)
            _pendingCount.value = outbox.size()
        }
        val ws = current
        if (connected && ws != null) {
            val ok = ws.send(env.toJson())
            appendLog("-> ${env.type} ${env.messageId.take(8)}${if (ok) "" else " (send buffer refused)"}")
        } else if (!durable) {
            appendLog("x  ${env.type} dropped (offline, non-durable)")
        } else {
            appendLog("~  ${env.type} queued (offline)")
        }
    }

    fun sendAck(inReplyTo: String) = send(Envelope.ack(inReplyTo), durable = false)

    fun sendError(inReplyTo: String?, code: String, message: String) = send(Envelope.error(code, message, inReplyTo), durable = false)

    /** Called by the app when the operator presses emergency stop locally. */
    fun latchEmergencyStop() {
        AppLog.w(TAG, "emergency stop latched locally")
        store.emergencyStopLatched = true
        _emergencyStopActive.value = true
    }

    // ------------------------------------------------------------------ connection loop

    private suspend fun connectLoop() {
        var attempt = 0
        while (scope.isActive) {
            val pairing = store.pairing.value
            if (pairing == null) {
                _state.value = ConnectionState.Unpaired
                store.pairing.filterNotNull().first()
                attempt = 0
                continue
            }
            _state.value = ConnectionState.Connecting
            val reason = runSession(pairing)
            heartbeatJob?.cancel()
            connected = false
            current = null
            if (store.pairing.value == null) continue
            val wait = backoffSeconds(attempt)
            attempt++
            _state.value = ConnectionState.Backoff(wait, reason)
            _lastFailure.value = AppLog.sanitize(reason)
            AppLog.w(TAG, "connection lost/failed: $reason; retry in ${wait}s")
            appendLog("backoff ${wait}s: $reason")
            delay(wait * 1000L)
        }
    }

    private fun backoffSeconds(attempt: Int): Int {
        val base = min(60, 1 shl min(attempt, 6))
        return min(60, base + Random.nextInt(0, 2))
    }

    /** Opens one socket and suspends until it closes. Returns the close reason. */
    private suspend fun runSession(pairing: Pairing): String {
        val client: OkHttpClient = runCatching { FingerprintTrust.pinnedClient(pairing.tlsFingerprint) }
            .getOrElse { return "bad pinned fingerprint: ${it.message}" }
        val request = Request.Builder()
            .url(pairing.wsUrl)
            .header("Authorization", "Bearer ${pairing.deviceToken}")
            .build()
        val closed = CompletableDeferred<String>()
        closedSignal = closed
        val opened = CompletableDeferred<Unit>()
        val ws = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                current = webSocket
                connected = true
                opened.complete(Unit)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleInbound(text)
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(1000, null)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                connected = false
                closed.complete("closed $code ${reason.ifBlank { "" }}".trim())
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                connected = false
                val http = response?.code?.let { " (HTTP $it)" } ?: ""
                closed.complete("${t.javaClass.simpleName}: ${t.message ?: ""}$http".trim())
            }
        })
        current = ws
        val openJob = scope.launch {
            opened.await()
            onOpened(pairing)
        }
        try {
            return closed.await()
        } finally {
            openJob.cancel()
            heartbeatJob?.cancel()
            ws.cancel()
            client.dispatcher.executorService.shutdown()
            client.connectionPool.evictAll()
        }
    }

    private fun onOpened(pairing: Pairing) {
        _state.value = ConnectionState.Connected(pairing.backendName)
        _lastFailure.value = null
        AppLog.i(TAG, "connected to ${pairing.host}:${pairing.port}")
        appendLog("connected to ${pairing.host}:${pairing.port}")
        send(
            Envelope.of(
                MessageType.RECONNECT_REQUEST,
                ReconnectRequest(pairing.deviceId, lastReceivedMessageId, outbox.size()),
                ReconnectRequest.serializer(),
            ),
            durable = false,
        )
        val pending = outbox.snapshot()
        if (pending.isNotEmpty()) appendLog("replaying ${pending.size} queued envelope(s)")
        pending.forEach { current?.send(it.toJson()) }
        heartbeatJob?.cancel()
        heartbeatJob = scope.launch {
            while (isActive && connected) {
                heartbeatProvider()?.let { hb ->
                    send(Envelope.of(MessageType.HEARTBEAT, hb, Heartbeat.serializer()), durable = false)
                }
                delay(HEARTBEAT_INTERVAL_MS)
            }
        }
    }

    // ------------------------------------------------------------------ inbound

    private fun handleInbound(text: String) {
        val env = Envelope.parseOrNull(text) ?: run {
            appendLog("<- unparsable message ignored")
            AppLog.w(TAG, "unparsable inbound message ignored (${text.length} chars)")
            return
        }
        if (!env.isSupportedVersion) {
            sendError(env.messageId, "unsupported_version", "device speaks protocol ${com.fitron.sellagent.protocol.PROTOCOL_VERSION}")
            return
        }
        val duplicate = synchronized(seenLock) { seen.put(env.messageId, true) != null }
        if (duplicate) {
            if (env.type in MessageType.ACK_EXPECTED) sendAck(env.messageId)
            appendLog("<- duplicate ${env.type} ${env.messageId.take(8)} ignored")
            return
        }
        lastReceivedMessageId = env.messageId
        appendLog("<- ${env.type} ${env.messageId.take(8)}")
        if (!env.isKnownType) {
            // Forward compatibility: newer backends may send types this build does not know. Log, never ack, never throw.
            AppLog.i(TAG, "ignored unknown message type '${env.type.take(40)}'")
            return
        }
        when (env.type) {
            MessageType.EVENT -> {
                val ev = runCatching { env.payloadAs<EventPayload>() }.getOrNull()
                _lastEvent.value = ev
                AppLog.i(TAG, "backend event '${ev?.name?.take(60) ?: "?"}'")
            }
            MessageType.ACK, MessageType.EMERGENCY_STOP_ACK -> {
                val id = env.inReplyTo ?: runCatching { env.payloadAs<Ack>().messageId }.getOrNull()
                if (id != null && outbox.remove(id)) _pendingCount.value = outbox.size()
            }
            MessageType.HEARTBEAT_ACK -> {
                _lastHeartbeatAckAt.value = System.currentTimeMillis()
                runCatching { env.payloadAs<HeartbeatAck>() }.getOrNull()?.let { applyEmergencyFlag(it.emergencyStopActive) }
            }
            MessageType.RECONNECT_RESPONSE -> {
                runCatching { env.payloadAs<ReconnectResponse>() }.getOrNull()?.let { applyEmergencyFlag(it.emergencyStopActive) }
            }
            MessageType.EMERGENCY_STOP -> {
                applyEmergencyFlag(true)
                emit(env)
            }
            MessageType.ERROR -> {
                // A rejected durable envelope must not be replayed forever.
                val id = env.inReplyTo
                if (id != null && outbox.remove(id)) _pendingCount.value = outbox.size()
                val err = runCatching { env.payloadAs<ErrorEvent>() }.getOrNull()
                appendLog("   error ${err?.code ?: "?"}: ${err?.message?.take(80) ?: ""}")
                AppLog.w(TAG, "backend error ${err?.code ?: "?"}: ${err?.message?.take(200) ?: ""}")
                emit(env)
            }
            else -> emit(env)
        }
    }

    private fun applyEmergencyFlag(active: Boolean) {
        if (_emergencyStopActive.value != active) AppLog.w(TAG, "emergency stop ${if (active) "ACTIVE" else "cleared by PC"}")
        store.emergencyStopLatched = active
        _emergencyStopActive.value = active
    }

    private fun emit(env: Envelope) {
        if (!_inbound.tryEmit(env)) scope.launch { _inbound.emit(env) }
    }

    private fun appendLog(line: String) {
        AppLog.d(TAG, line)
        val stamp = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm:ss"))
        _log.value = (_log.value + "$stamp ${AppLog.sanitize(line)}").takeLast(80)
    }

    private companion object {
        const val HEARTBEAT_INTERVAL_MS = 20_000L
        const val TAG = "socket"
        val CERT_MARKERS = listOf("SSLHandshake", "CertificateException", "pinned fingerprint", "SSLPeerUnverified", "certificate")
    }
}
