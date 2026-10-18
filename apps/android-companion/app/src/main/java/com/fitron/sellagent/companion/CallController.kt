package com.fitron.sellagent.companion

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.telecom.TelecomManager
import androidx.core.content.ContextCompat
import com.fitron.sellagent.R
import com.fitron.sellagent.core.CoreContainer
import com.fitron.sellagent.core.log.AppLog
import com.fitron.sellagent.core.service.ConnectionForegroundService
import com.fitron.sellagent.core.telecom.AudioRouting
import com.fitron.sellagent.core.telecom.SellAgentInCallService
import com.fitron.sellagent.protocol.CallMode
import com.fitron.sellagent.protocol.CallRequest
import com.fitron.sellagent.protocol.CallState
import com.fitron.sellagent.protocol.CallStateEvent
import com.fitron.sellagent.protocol.CallStateSource
import com.fitron.sellagent.protocol.CancelRequest
import com.fitron.sellagent.protocol.EmergencyStop
import com.fitron.sellagent.protocol.Envelope
import com.fitron.sellagent.protocol.MessageType
import com.fitron.sellagent.protocol.parseIsoInstant
import com.fitron.sellagent.protocol.payloadAs
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer
import com.fitron.sellagent.protocol.ProtocolJson
import java.io.File

data class PendingCall(val request: CallRequest, val envelopeId: String, val receivedAtMs: Long, val expiresAtMs: Long)

/** Local history of one call job, built only from call.state events this phone sent. Persisted in files/call_logs.json. */
@Serializable
data class CallLogEntry(
    val callJobId: String,
    val number: String,
    val displayName: String? = null,
    val receivedAtMs: Long,
    val dialedAtMs: Long? = null,
    val connectedAtMs: Long? = null,
    val endedAtMs: Long? = null,
    val finalState: String = CallState.REQUESTED,
    val events: List<String> = emptyList(),
) {
    /** Talk time from the first ACTIVE/OFFHOOK to the end; null when the call never connected. */
    val durationSeconds: Long?
        get() = if (connectedAtMs != null) (((endedAtMs ?: System.currentTimeMillis()) - connectedAtMs) / 1000).coerceAtLeast(0) else null
}

data class ActiveJob(val callJobId: String, val number: String, val dialedAtMs: Long, val lastState: String, val lastSource: String)

/**
 * Campaign-call flow on the phone.
 *
 *  call.request  -> validated; acked only when the operator CAN dial; shown as a card. Human-assisted mode requires the
 *                   operator to TAP "Dial" (never auto-dial). Autonomous mode is always refused with an error envelope
 *                   ("autonomous mode not enabled on device") - there is no release-gate flag on the device yet.
 *  call.cancel   -> ends the call through InCallService when bound, otherwise shows a prominent "Hang up now" instruction.
 *  emergency stop-> from the PC or the local button: latch, end the call if possible, refuse all dialing until a
 *                   heartbeat_ack / reconnect_ack reports emergency_stop_active=false.
 *  call.state    -> one event per TelephonyCallback / InCallService state change, tagged with the call_job_id.
 */
class CallController(private val context: Context, private val core: CoreContainer) {
    private val _queue = MutableStateFlow<List<PendingCall>>(emptyList())
    /** Pending call.requests, oldest first. Each needs an operator tap. */
    val queue: StateFlow<List<PendingCall>> = _queue

    private val logFile = File(context.filesDir, "call_logs.json")
    private val _logs = MutableStateFlow(loadLogs())
    val logs: StateFlow<List<CallLogEntry>> = _logs

    private val _active = MutableStateFlow<ActiveJob?>(null)
    val active: StateFlow<ActiveJob?> = _active

    private val _hangupInstruction = MutableStateFlow<String?>(null)
    val hangupInstruction: StateFlow<String?> = _hangupInstruction

    private val _events = MutableStateFlow<List<String>>(emptyList())
    val events: StateFlow<List<String>> = _events

    private val expiryJobs = HashMap<String, Job>()
    private var lastCoarse: String? = null
    private var lastDetailed: String? = null

    init {
        core.scope.launch { core.socket.inbound.collect { handle(it) } }
        core.scope.launch {
            core.callMonitor.events.collect { ev ->
                val job = _active.value ?: return@collect
                if (ev.protocolState == lastCoarse) return@collect
                lastCoarse = ev.protocolState
                sendState(job.callJobId, ev.protocolState, CallStateSource.TELEPHONY_CALLBACK, detail = "TelephonyCallback state ${ev.telephonyState}")
                if (ev.protocolState == CallState.IDLE && job.lastState != CallState.REQUESTED) finishJob("telephony idle")
            }
        }
        core.scope.launch {
            SellAgentInCallService.events.collect { ev ->
                val job = _active.value ?: return@collect
                val key = "${ev.protocolState}:${ev.disconnectCause}"
                if (key == lastDetailed) return@collect
                lastDetailed = key
                sendState(job.callJobId, ev.protocolState, CallStateSource.IN_CALL_SERVICE, route = ev.audioRoute, cause = ev.disconnectCause, detail = SellAgentInCallService.describeState(ev.telecomState))
                if (ev.protocolState == CallState.DISCONNECTED) {
                    delay(1500)
                    finishJob("in_call_service disconnected")
                }
            }
        }
        core.scope.launch {
            core.socket.emergencyStopActive.collect { active -> if (active) log(context.getString(R.string.calls_estop_latched)) }
        }
    }

    val emergencyStopActive: Boolean get() = core.socket.emergencyStopActive.value

    // ------------------------------------------------------------------ inbound

    private fun handle(env: Envelope) {
        when (env.type) {
            MessageType.CALL_REQUEST -> onCallRequest(env)
            MessageType.CALL_CANCEL -> onCancel(env)
            MessageType.EMERGENCY_STOP -> onRemoteEmergencyStop()
            else -> Unit
        }
    }

    private fun onCallRequest(env: Envelope) {
        val req = runCatching { env.payloadAs<CallRequest>() }.getOrElse {
            core.socket.sendError(env.messageId, "invalid_call_request", "could not parse call.request: ${it.message}")
            return
        }
        val expiresAt = parseIsoInstant(req.expiresAt)?.toEpochMilli()
        val now = System.currentTimeMillis()
        val refusal: Pair<String, String>? = when {
            emergencyStopActive -> "emergency_stop_active" to "emergency stop is active on the device"
            req.mode == CallMode.AUTONOMOUS -> "autonomous_disabled" to "autonomous mode not enabled on device"
            req.mode != CallMode.HUMAN_ASSISTED -> "unsupported_mode" to "unsupported call mode ${req.mode}"
            expiresAt == null -> "invalid_expiry" to "expires_at could not be parsed"
            expiresAt <= now -> "expired" to "call request already expired"
            req.authorizationToken.length < 16 -> "invalid_authorization" to "authorization_token missing"
            ContextCompat.checkSelfPermission(context, Manifest.permission.CALL_PHONE) != PackageManager.PERMISSION_GRANTED ->
                "call_phone_not_granted" to "CALL_PHONE permission not granted on the device"
            core.uiPrefs.queuePaused.value -> "queue_paused" to "call queue paused on the device by the operator"
            _queue.value.any { it.request.callJobId == req.callJobId } -> "duplicate_job" to "call job already queued"
            _queue.value.size >= MAX_QUEUE -> "queue_full" to "device queue is full ($MAX_QUEUE)"
            else -> null
        }
        if (refusal != null) {
            core.socket.sendError(env.messageId, refusal.first, refusal.second)
            sendState(req.callJobId, CallState.REJECTED, CallStateSource.APP, detail = refusal.second)
            log("call.request ${req.callJobId.take(8)} refused: ${refusal.first}")
            return
        }
        core.socket.sendAck(env.messageId)
        requireNotNull(expiresAt)
        _queue.value = _queue.value + PendingCall(req, env.messageId, now, expiresAt)
        upsertLog(req.callJobId) { it ?: CallLogEntry(req.callJobId, req.e164Number, req.displayName, now) }
        sendState(req.callJobId, CallState.REQUESTED, CallStateSource.APP, detail = "shown to operator; waiting for tap")
        ConnectionForegroundService.start(context, context.getString(R.string.fgs_reason_call_expected))
        log("call.request ${req.callJobId.take(8)} for ${mask(req.e164Number)} (${req.mode}) queued for operator")
        expiryJobs[req.callJobId]?.cancel()
        expiryJobs[req.callJobId] = core.scope.launch {
            delay((expiresAt - now).coerceAtLeast(0))
            if (removeFromQueue(req.callJobId) != null) {
                sendState(req.callJobId, CallState.REJECTED, CallStateSource.APP, detail = "operator did not dial before expires_at")
                log("call.request ${req.callJobId.take(8)} expired without a tap")
                stopServiceIfIdle()
            }
        }
    }

    private fun onCancel(env: Envelope) {
        val cancel = runCatching { env.payloadAs<CancelRequest>() }.getOrNull() ?: return
        if (removeFromQueue(cancel.callJobId) != null) {
            sendState(cancel.callJobId, CallState.REJECTED, CallStateSource.APP, detail = "cancelled before dialing: ${cancel.reason}")
            log("call.cancel for queued ${cancel.callJobId.take(8)}: ${cancel.reason}")
            stopServiceIfIdle()
            return
        }
        val a = _active.value
        if (a != null && a.callJobId == cancel.callJobId) {
            val ended = SellAgentInCallService.endActiveCall()
            if (ended) {
                log("call.cancel: call ended via InCallService")
                sendState(a.callJobId, CallState.DISCONNECTED, CallStateSource.APP, detail = "ended via InCallService on call.cancel: ${cancel.reason}")
            } else {
                _hangupInstruction.value = context.getString(R.string.calls_hang_up_now, cancel.reason)
                sendState(a.callJobId, CallState.UNKNOWN, CallStateSource.APP, detail = "cancel received; app is not the default dialer, operator must hang up manually")
                log("call.cancel: cannot end call (InCallService not bound) - operator must hang up")
            }
            return
        }
        log("call.cancel for unknown job ${cancel.callJobId.take(8)} ignored")
    }

    private fun onRemoteEmergencyStop() {
        log("safety.emergency_stop received from PC")
        stopEverything("emergency stop from PC")
    }

    // ------------------------------------------------------------------ operator actions

    /** Operator tapped Dial on a queue row (or the first row when [callJobId] is null). Returns a user-visible outcome. */
    fun dial(callJobId: String? = null): String {
        val p = (if (callJobId == null) _queue.value.firstOrNull() else _queue.value.firstOrNull { it.request.callJobId == callJobId })
            ?: return context.getString(R.string.calls_no_pending)
        if (emergencyStopActive) return context.getString(R.string.call_emergency_blocked)
        if (_active.value != null || core.inCall) return context.getString(R.string.calls_busy_in_call)
        if (System.currentTimeMillis() > p.expiresAtMs) {
            removeFromQueue(p.request.callJobId)
            sendState(p.request.callJobId, CallState.REJECTED, CallStateSource.APP, detail = "expired when operator tapped")
            return context.getString(R.string.calls_expired)
        }
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CALL_PHONE) != PackageManager.PERMISSION_GRANTED) {
            return context.getString(R.string.call_dial_denied)
        }
        val tm = context.getSystemService(Context.TELECOM_SERVICE) as? TelecomManager ?: return "TelecomManager unavailable"
        return try {
            lastCoarse = null
            lastDetailed = null
            tm.placeCall(Uri.fromParts("tel", p.request.e164Number, null), Bundle())
            removeFromQueue(p.request.callJobId)
            _active.value = ActiveJob(p.request.callJobId, p.request.e164Number, System.currentTimeMillis(), CallState.DIALING, CallStateSource.APP)
            upsertLog(p.request.callJobId) { (it ?: CallLogEntry(p.request.callJobId, p.request.e164Number, p.request.displayName, p.receivedAtMs)).copy(dialedAtMs = System.currentTimeMillis()) }
            sendState(p.request.callJobId, CallState.DIALING, CallStateSource.APP, detail = "TelecomManager.placeCall issued by operator tap")
            p.request.requestedRoute?.let { route ->
                core.scope.launch {
                    delay(2500)
                    val r = AudioRouting.setRoute(context, route)
                    log("requested_route $route via ${r.apiUsed}: ok=${r.ok}")
                }
            }
            ConnectionForegroundService.start(context, context.getString(R.string.fgs_reason_call_active))
            log("dialed ${mask(p.request.e164Number)} for job ${p.request.callJobId.take(8)}")
            context.getString(R.string.call_dial_result_ok)
        } catch (e: Exception) {
            sendState(p.request.callJobId, CallState.FAILED, CallStateSource.APP, cause = e.javaClass.simpleName, detail = e.message)
            removeFromQueue(p.request.callJobId)
            log("placeCall failed: ${e.javaClass.simpleName}")
            "${e.javaClass.simpleName}: ${e.message}"
        }
    }

    /** Operator declined a queued request. */
    fun decline(callJobId: String, reason: String) {
        val p = removeFromQueue(callJobId) ?: return
        sendState(p.request.callJobId, CallState.REJECTED, CallStateSource.APP, detail = "operator declined: $reason")
        log("operator declined ${p.request.callJobId.take(8)}")
        stopServiceIfIdle()
    }

    /** Pausing refuses NEW requests with error queue_paused; already queued rows stay until dialed/declined/expired. */
    fun setQueuePaused(paused: Boolean) {
        core.uiPrefs.setQueuePaused(paused)
        log(if (paused) "queue paused by operator" else "queue resumed by operator")
    }

    /** Toggle speaker <-> earpiece for the current call; returns the API outcome. */
    fun toggleSpeaker(): String {
        val target = if (AudioRouting.currentRoute(context) == com.fitron.sellagent.protocol.AudioRoute.SPEAKER) {
            com.fitron.sellagent.protocol.AudioRoute.EARPIECE
        } else {
            com.fitron.sellagent.protocol.AudioRoute.SPEAKER
        }
        val r = AudioRouting.setRoute(context, target)
        log("route $target via ${r.apiUsed}: ok=${r.ok}")
        return "${r.apiUsed}: ${if (r.ok) target else r.detail}"
    }

    /** Operator ends the active call (works only when our InCallService is bound). */
    fun endCall(): Boolean {
        val ok = SellAgentInCallService.endActiveCall()
        log("end call via InCallService: $ok")
        return ok
    }

    /** Local emergency stop: latch, notify PC, end call if possible, block dialing until cleared from the PC. */
    fun emergencyStop(reason: String) {
        core.socket.latchEmergencyStop()
        core.socket.send(Envelope.of(MessageType.EMERGENCY_STOP, EmergencyStop(reason = reason, issuedBy = "android"), EmergencyStop.serializer()), durable = true)
        log("EMERGENCY STOP pressed: $reason")
        stopEverything(reason)
    }

    fun clearHangupInstruction() {
        _hangupInstruction.value = null
    }

    // ------------------------------------------------------------------ helpers

    private fun stopEverything(reason: String) {
        _queue.value.toList().forEach { p ->
            removeFromQueue(p.request.callJobId)
            sendState(p.request.callJobId, CallState.REJECTED, CallStateSource.APP, detail = "emergency stop: $reason")
        }
        val a = _active.value
        if (a != null) {
            val ended = SellAgentInCallService.endActiveCall()
            if (!ended) {
                _hangupInstruction.value = context.getString(R.string.calls_hang_up_now, reason)
                sendState(a.callJobId, CallState.UNKNOWN, CallStateSource.APP, detail = "emergency stop; app cannot end the call (not default dialer), operator must hang up")
            }
        }
        if (a == null) ConnectionForegroundService.stop(context)
    }

    private fun finishJob(reason: String) {
        val a = _active.value ?: return
        _active.value = null
        _hangupInstruction.value = null
        upsertLog(a.callJobId) { it?.copy(endedAtMs = it.endedAtMs ?: System.currentTimeMillis()) }
        log("job ${a.callJobId.take(8)} finished ($reason)")
        stopServiceIfIdle()
    }

    private fun stopServiceIfIdle() {
        if (_queue.value.isEmpty() && _active.value == null) ConnectionForegroundService.stop(context)
    }

    private fun removeFromQueue(callJobId: String): PendingCall? {
        val p = _queue.value.firstOrNull { it.request.callJobId == callJobId } ?: return null
        _queue.value = _queue.value.filterNot { it.request.callJobId == callJobId }
        expiryJobs.remove(callJobId)?.cancel()
        return p
    }

    @Synchronized
    private fun upsertLog(callJobId: String, f: (CallLogEntry?) -> CallLogEntry?) {
        val list = _logs.value.toMutableList()
        val idx = list.indexOfFirst { it.callJobId == callJobId }
        val updated = f(if (idx >= 0) list[idx] else null) ?: return
        if (idx >= 0) list[idx] = updated else list.add(0, updated)
        _logs.value = list.take(200)
        runCatching { logFile.writeText(ProtocolJson.encodeToString(ListSerializer(CallLogEntry.serializer()), _logs.value)) }
    }

    private fun loadLogs(): List<CallLogEntry> = runCatching {
        if (logFile.exists()) ProtocolJson.decodeFromString(ListSerializer(CallLogEntry.serializer()), logFile.readText()) else emptyList()
    }.getOrDefault(emptyList())

    fun clearLogs() {
        _logs.value = emptyList()
        runCatching { logFile.delete() }
    }

    private fun sendState(callJobId: String, state: String, source: String, route: String? = null, cause: String? = null, detail: String? = null) {
        val ev = CallStateEvent(
            callJobId = callJobId,
            state = state,
            audioRoute = route ?: AudioRouting.currentRoute(context),
            disconnectCause = cause,
            source = source,
            detail = detail?.take(300),
        )
        core.socket.send(Envelope.of(MessageType.CALL_STATE, ev, CallStateEvent.serializer()), durable = true)
        AppLog.i("call.state", "job ${callJobId.take(8)} -> $state ($source)${cause?.let { " cause=$it" } ?: ""}")
        val nowMs = System.currentTimeMillis()
        val stamp = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm:ss"))
        upsertLog(callJobId) { e ->
            e?.copy(
                finalState = state,
                connectedAtMs = e.connectedAtMs ?: if (state == CallState.ACTIVE || state == CallState.OFFHOOK) nowMs else null,
                endedAtMs = if (state in TERMINAL) (e.endedAtMs ?: nowMs) else e.endedAtMs,
                events = (e.events + "$stamp $state ($source)${cause?.let { c -> " $c" } ?: ""}").takeLast(40),
            )
        }
        _active.value?.let { if (it.callJobId == callJobId) _active.value = it.copy(lastState = state, lastSource = source) }
    }

    private fun log(line: String) {
        AppLog.i("calls", line)
        val stamp = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm:ss"))
        _events.value = (_events.value + "$stamp $line").takeLast(100)
    }

    companion object {
        const val MAX_QUEUE = 10
        private val TERMINAL = setOf(CallState.DISCONNECTED, CallState.IDLE, CallState.FAILED, CallState.REJECTED)

        fun mask(number: String): String = if (number.length > 6) number.take(3) + "…" + number.takeLast(3) else "…"
    }
}
