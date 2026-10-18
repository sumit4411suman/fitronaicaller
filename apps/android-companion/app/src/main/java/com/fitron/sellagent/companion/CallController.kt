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

data class PendingCall(val request: CallRequest, val envelopeId: String, val receivedAtMs: Long, val expiresAtMs: Long)

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
    private val _pending = MutableStateFlow<PendingCall?>(null)
    val pending: StateFlow<PendingCall?> = _pending

    private val _active = MutableStateFlow<ActiveJob?>(null)
    val active: StateFlow<ActiveJob?> = _active

    private val _hangupInstruction = MutableStateFlow<String?>(null)
    val hangupInstruction: StateFlow<String?> = _hangupInstruction

    private val _events = MutableStateFlow<List<String>>(emptyList())
    val events: StateFlow<List<String>> = _events

    private var expiryJob: Job? = null
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
            _pending.value != null || _active.value != null -> "busy" to "device already has a pending or active call job"
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
        _pending.value = PendingCall(req, env.messageId, now, expiresAt)
        _hangupInstruction.value = null
        sendState(req.callJobId, CallState.REQUESTED, CallStateSource.APP, detail = "shown to operator; waiting for tap")
        ConnectionForegroundService.start(context, context.getString(R.string.fgs_reason_call_expected))
        log("call.request ${req.callJobId.take(8)} for ${mask(req.e164Number)} (${req.mode}) shown to operator")
        expiryJob?.cancel()
        expiryJob = core.scope.launch {
            delay((expiresAt - now).coerceAtLeast(0))
            val p = _pending.value
            if (p != null && p.request.callJobId == req.callJobId) {
                _pending.value = null
                sendState(req.callJobId, CallState.REJECTED, CallStateSource.APP, detail = "operator did not dial before expires_at")
                log("call.request ${req.callJobId.take(8)} expired without a tap")
                if (_active.value == null) ConnectionForegroundService.stop(context)
            }
        }
    }

    private fun onCancel(env: Envelope) {
        val cancel = runCatching { env.payloadAs<CancelRequest>() }.getOrNull() ?: return
        val p = _pending.value
        if (p != null && p.request.callJobId == cancel.callJobId) {
            _pending.value = null
            expiryJob?.cancel()
            sendState(cancel.callJobId, CallState.REJECTED, CallStateSource.APP, detail = "cancelled before dialing: ${cancel.reason}")
            log("call.cancel for pending ${cancel.callJobId.take(8)}: ${cancel.reason}")
            if (_active.value == null) ConnectionForegroundService.stop(context)
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

    /** Operator tapped Dial on the pending card. Returns a user-visible outcome string. */
    fun dial(): String {
        val p = _pending.value ?: return context.getString(R.string.calls_no_pending)
        if (emergencyStopActive) return context.getString(R.string.call_emergency_blocked)
        if (System.currentTimeMillis() > p.expiresAtMs) {
            _pending.value = null
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
            expiryJob?.cancel()
            _pending.value = null
            _active.value = ActiveJob(p.request.callJobId, p.request.e164Number, System.currentTimeMillis(), CallState.DIALING, CallStateSource.APP)
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
            _pending.value = null
            log("placeCall failed: ${e.javaClass.simpleName}")
            "${e.javaClass.simpleName}: ${e.message}"
        }
    }

    /** Operator declined the pending request. */
    fun decline(reason: String) {
        val p = _pending.value ?: return
        _pending.value = null
        expiryJob?.cancel()
        sendState(p.request.callJobId, CallState.REJECTED, CallStateSource.APP, detail = "operator declined: $reason")
        log("operator declined ${p.request.callJobId.take(8)}")
        if (_active.value == null) ConnectionForegroundService.stop(context)
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
        val p = _pending.value
        if (p != null) {
            _pending.value = null
            expiryJob?.cancel()
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
        log("job ${a.callJobId.take(8)} finished ($reason)")
        if (_pending.value == null) ConnectionForegroundService.stop(context)
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
        _active.value?.let { if (it.callJobId == callJobId) _active.value = it.copy(lastState = state, lastSource = source) }
    }

    private fun log(line: String) {
        val stamp = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm:ss"))
        _events.value = (_events.value + "$stamp $line").takeLast(100)
    }

    companion object {
        fun mask(number: String): String = if (number.length > 6) number.take(3) + "…" + number.takeLast(3) else "…"
    }
}
