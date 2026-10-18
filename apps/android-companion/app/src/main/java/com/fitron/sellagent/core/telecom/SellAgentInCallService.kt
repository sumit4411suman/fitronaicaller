package com.fitron.sellagent.core.telecom

import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.telecom.Call
import android.telecom.CallAudioState
import android.telecom.DisconnectCause
import android.telecom.InCallService
import com.fitron.sellagent.core.log.AppLog
import com.fitron.sellagent.protocol.AudioRoute
import com.fitron.sellagent.protocol.CallState
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow

/** One detailed call-state change observed through android.telecom.Call.Callback. */
data class DetailedCallEvent(
    val telecomState: Int,
    val protocolState: String,
    val disconnectCause: String?,
    val audioRoute: String,
    val atMillis: Long = System.currentTimeMillis(),
)

/**
 * The InCallService is bound by the system ONLY while this app holds the default dialer role (RoleManager.ROLE_DIALER).
 * It is the documented way to observe detailed call states, set the audio route and end a call. The service keeps
 * a minimal UI contract: it does not render an in-call screen itself; the app's activity shows the state.
 */
class SellAgentInCallService : InCallService() {

    private val callback = object : Call.Callback() {
        override fun onStateChanged(call: Call, state: Int) = publish(call)
        override fun onDetailsChanged(call: Call, details: Call.Details) = publish(call)
    }

    override fun onBind(intent: Intent?): IBinder? {
        instance = this
        _bound.value = true
        return super.onBind(intent)
    }

    override fun onUnbind(intent: Intent?): Boolean {
        _bound.value = false
        instance = null
        _calls.value = emptyList()
        return super.onUnbind(intent)
    }

    override fun onCallAdded(call: Call) {
        call.registerCallback(callback)
        _calls.value = _calls.value + call
        publish(call)
    }

    override fun onCallRemoved(call: Call) {
        call.unregisterCallback(callback)
        _calls.value = _calls.value - call
        publish(call)
        updateWifiObservation()
    }

    @Deprecated("Platform callback kept for API 29-33; API 34 adds onCallEndpointChanged")
    @Suppress("DEPRECATION")
    override fun onCallAudioStateChanged(audioState: CallAudioState?) {
        super.onCallAudioStateChanged(audioState)
        audioState?.let {
            _audioRoute.value = routeOf(it.route)
            _muted.value = it.isMuted
            _supportedRoutes.value = listOf(
                CallAudioState.ROUTE_EARPIECE, CallAudioState.ROUTE_SPEAKER, CallAudioState.ROUTE_BLUETOOTH, CallAudioState.ROUTE_WIRED_HEADSET,
            ).filter { r -> it.supportedRouteMask and r != 0 }.map { r -> routeOf(r) }
        }
    }

    private fun publish(call: Call) {
        val state = stateOf(call)
        updateWifiObservation()
        if (state == Call.STATE_ACTIVE && _activeSinceMs.value == null) _activeSinceMs.value = System.currentTimeMillis()
        if (activeCall() == null) _activeSinceMs.value = null
        val cause = runCatching { call.details?.disconnectCause }.getOrNull()
        val event = DetailedCallEvent(
            telecomState = state,
            protocolState = mapState(state),
            disconnectCause = cause?.let { describeCause(it) },
            audioRoute = _audioRoute.value,
        )
        _lastEvent.value = event
        _events.tryEmit(event)
        AppLog.i("incall", "call ${describeState(state)} route=${event.audioRoute}${event.disconnectCause?.let { " cause=$it" } ?: ""}")
    }

    companion object {
        private var instance: SellAgentInCallService? = null

        private val _bound = MutableStateFlow(false)
        val bound: StateFlow<Boolean> = _bound

        private val _calls = MutableStateFlow<List<Call>>(emptyList())
        val calls: StateFlow<List<Call>> = _calls

        private val _audioRoute = MutableStateFlow(AudioRoute.UNKNOWN)
        val audioRoute: StateFlow<String> = _audioRoute

        private val _supportedRoutes = MutableStateFlow<List<String>>(emptyList())
        /** Routes the platform reports as supported for the current call (CallAudioState.supportedRouteMask). */
        val supportedRoutes: StateFlow<List<String>> = _supportedRoutes

        private val _muted = MutableStateFlow(false)
        val muted: StateFlow<Boolean> = _muted

        /** Wall-clock millis when the current call became ACTIVE (null when no call is active). */
        private val _activeSinceMs = MutableStateFlow<Long?>(null)
        val activeSinceMs: StateFlow<Long?> = _activeSinceMs

        /**
         * Wi-Fi calling fact: true/false only while a call is present and Call.Details.PROPERTY_WIFI could be read;
         * null otherwise ("unknown"). This is the ONLY source for wifi_calling_active - there is no public API that
         * answers it outside a call.
         */
        private val _wifiCallObserved = MutableStateFlow<Boolean?>(null)
        val wifiCallObserved: StateFlow<Boolean?> = _wifiCallObserved

        private fun updateWifiObservation() {
            val call = activeCall()
            _wifiCallObserved.value = if (call == null) null else runCatching { call.details?.hasProperty(Call.Details.PROPERTY_WIFI) }.getOrNull()
        }

        /** Mute/unmute the microphone through InCallService.setMuted. Returns false when not bound. */
        fun setMutedCompat(muted: Boolean): Boolean {
            val svc = instance ?: return false
            return runCatching { svc.setMuted(muted); _muted.value = muted; true }.getOrDefault(false)
        }

        fun holdActive(hold: Boolean): Boolean {
            if (instance == null) return false
            val call = activeCall() ?: return false
            return runCatching { if (hold) call.hold() else call.unhold(); true }.getOrDefault(false)
        }

        fun playDtmf(digit: Char): Boolean {
            if (instance == null) return false
            val call = activeCall() ?: return false
            return runCatching { call.playDtmfTone(digit); call.stopDtmfTone(); true }.getOrDefault(false)
        }

        private val _lastEvent = MutableStateFlow<DetailedCallEvent?>(null)
        val lastEvent: StateFlow<DetailedCallEvent?> = _lastEvent

        private val _events = MutableSharedFlow<DetailedCallEvent>(extraBufferCapacity = 64)
        val events: SharedFlow<DetailedCallEvent> = _events

        /** Current (non-disconnected) call, if any. */
        fun activeCall(): Call? = _calls.value.firstOrNull { stateOf(it) != Call.STATE_DISCONNECTED }

        /** Ends the active call through InCallService. Returns false when not bound or no call. */
        fun endActiveCall(): Boolean {
            if (instance == null) return false
            val call = activeCall() ?: return false
            return runCatching { call.disconnect(); true }.getOrDefault(false)
        }

        /** Sets the route through InCallService.setAudioRoute. Returns false when not bound. */
        fun setRoute(callAudioStateRoute: Int): Boolean {
            val svc = instance ?: return false
            return runCatching { svc.setAudioRoute(callAudioStateRoute); true }.getOrDefault(false)
        }

        fun stateOf(call: Call): Int =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                call.details?.state ?: Call.STATE_NEW
            } else {
                legacyState(call)
            }

        @Suppress("DEPRECATION")
        private fun legacyState(call: Call): Int = call.state

        fun mapState(telecomState: Int): String = when (telecomState) {
            Call.STATE_NEW, Call.STATE_CONNECTING, Call.STATE_SELECT_PHONE_ACCOUNT -> CallState.REQUESTED
            Call.STATE_DIALING -> CallState.DIALING
            Call.STATE_RINGING -> CallState.RINGING
            Call.STATE_ACTIVE -> CallState.ACTIVE
            Call.STATE_HOLDING -> CallState.HOLDING
            Call.STATE_DISCONNECTING, Call.STATE_DISCONNECTED -> CallState.DISCONNECTED
            else -> CallState.UNKNOWN
        }

        fun describeState(telecomState: Int): String = when (telecomState) {
            Call.STATE_NEW -> "STATE_NEW"
            Call.STATE_DIALING -> "STATE_DIALING"
            Call.STATE_RINGING -> "STATE_RINGING"
            Call.STATE_HOLDING -> "STATE_HOLDING"
            Call.STATE_ACTIVE -> "STATE_ACTIVE"
            Call.STATE_DISCONNECTED -> "STATE_DISCONNECTED"
            Call.STATE_SELECT_PHONE_ACCOUNT -> "STATE_SELECT_PHONE_ACCOUNT"
            Call.STATE_CONNECTING -> "STATE_CONNECTING"
            Call.STATE_DISCONNECTING -> "STATE_DISCONNECTING"
            else -> "STATE_$telecomState"
        }

        fun describeCause(cause: DisconnectCause): String {
            val code = when (cause.code) {
                DisconnectCause.LOCAL -> "LOCAL"
                DisconnectCause.REMOTE -> "REMOTE"
                DisconnectCause.BUSY -> "BUSY"
                DisconnectCause.ERROR -> "ERROR"
                DisconnectCause.MISSED -> "MISSED"
                DisconnectCause.REJECTED -> "REJECTED"
                DisconnectCause.CANCELED -> "CANCELED"
                DisconnectCause.RESTRICTED -> "RESTRICTED"
                DisconnectCause.OTHER -> "OTHER"
                DisconnectCause.ANSWERED_ELSEWHERE -> "ANSWERED_ELSEWHERE"
                DisconnectCause.CALL_PULLED -> "CALL_PULLED"
                DisconnectCause.UNKNOWN -> "UNKNOWN"
                else -> "CODE_${cause.code}"
            }
            val reason = cause.reason?.takeIf { it.isNotBlank() }
            return if (reason != null) "$code ($reason)" else code
        }

        fun routeOf(callAudioStateRoute: Int): String = when (callAudioStateRoute) {
            CallAudioState.ROUTE_EARPIECE -> AudioRoute.EARPIECE
            CallAudioState.ROUTE_SPEAKER -> AudioRoute.SPEAKER
            CallAudioState.ROUTE_BLUETOOTH -> AudioRoute.BLUETOOTH
            CallAudioState.ROUTE_WIRED_HEADSET -> AudioRoute.WIRED_HEADSET
            else -> AudioRoute.UNKNOWN
        }

        fun callAudioStateRoute(protocolRoute: String): Int? = when (protocolRoute) {
            AudioRoute.EARPIECE -> CallAudioState.ROUTE_EARPIECE
            AudioRoute.SPEAKER -> CallAudioState.ROUTE_SPEAKER
            AudioRoute.BLUETOOTH -> CallAudioState.ROUTE_BLUETOOTH
            AudioRoute.WIRED_HEADSET -> CallAudioState.ROUTE_WIRED_HEADSET
            else -> null
        }
    }
}
