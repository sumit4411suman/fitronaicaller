package com.fitron.sellagent.core.telecom

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.telephony.PhoneStateListener
import android.telephony.TelephonyCallback
import android.telephony.TelephonyManager
import androidx.core.content.ContextCompat
import com.fitron.sellagent.core.log.AppLog
import com.fitron.sellagent.protocol.CallState
import java.util.concurrent.Executor
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow

/** One coarse state change from the telephony framework. */
data class CoarseCallState(val telephonyState: Int, val protocolState: String, val atMillis: Long = System.currentTimeMillis())

/**
 * Coarse call-state observation via the public TelephonyCallback.CallStateListener (API 31+) or, on API 29/30,
 * the deprecated PhoneStateListener. Requires READ_PHONE_STATE. Only IDLE / RINGING / OFFHOOK are available here;
 * detailed states come from the InCallService when the app is the default dialer.
 */
class CallMonitor(private val context: Context) {
    private val tm: TelephonyManager? = context.getSystemService(Context.TELEPHONY_SERVICE) as? TelephonyManager
    private val mainExecutor: Executor = ContextCompat.getMainExecutor(context)

    private val _state = MutableStateFlow(CoarseCallState(TelephonyManager.CALL_STATE_IDLE, CallState.IDLE))
    val state: StateFlow<CoarseCallState> = _state

    private val _registered = MutableStateFlow(false)
    val registered: StateFlow<Boolean> = _registered

    private val _events = MutableSharedFlow<CoarseCallState>(extraBufferCapacity = 64)
    val events: SharedFlow<CoarseCallState> = _events

    private var callback31: TelephonyCallback? = null

    @Suppress("DEPRECATION")
    private var legacyListener: PhoneStateListener? = null

    val inCall: Boolean get() = _state.value.telephonyState != TelephonyManager.CALL_STATE_IDLE

    /** Returns true when a listener is now registered. Safe to call repeatedly. */
    fun start(): Boolean {
        if (_registered.value) return true
        val manager = tm ?: return false
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_PHONE_STATE) != PackageManager.PERMISSION_GRANTED) return false
        return runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val cb = object : TelephonyCallback(), TelephonyCallback.CallStateListener {
                    override fun onCallStateChanged(state: Int) {
                        publish(state)
                    }
                }
                manager.registerTelephonyCallback(mainExecutor, cb)
                callback31 = cb
            } else {
                registerLegacy(manager)
            }
            _registered.value = true
            true
        }.getOrDefault(false)
    }

    @Suppress("DEPRECATION")
    private fun registerLegacy(manager: TelephonyManager) {
        val listener = object : PhoneStateListener() {
            @Deprecated("Deprecated in Java")
            override fun onCallStateChanged(state: Int, phoneNumber: String?) {
                publish(state)
            }
        }
        manager.listen(listener, PhoneStateListener.LISTEN_CALL_STATE)
        legacyListener = listener
    }

    @Suppress("DEPRECATION")
    private fun unregisterLegacy(manager: TelephonyManager) {
        legacyListener?.let { manager.listen(it, PhoneStateListener.LISTEN_NONE) }
    }

    fun stop() {
        val manager = tm ?: return
        runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                callback31?.let { manager.unregisterTelephonyCallback(it) }
            } else {
                unregisterLegacy(manager)
            }
        }
        callback31 = null
        legacyListener = null
        _registered.value = false
    }

    private fun publish(state: Int) {
        val mapped = when (state) {
            TelephonyManager.CALL_STATE_RINGING -> CallState.RINGING
            TelephonyManager.CALL_STATE_OFFHOOK -> CallState.OFFHOOK
            TelephonyManager.CALL_STATE_IDLE -> CallState.IDLE
            else -> CallState.UNKNOWN
        }
        val value = CoarseCallState(state, mapped)
        AppLog.i("telephony", "TelephonyCallback ${describe(state)}")
        _state.value = value
        _events.tryEmit(value)
    }

    companion object {
        fun describe(state: Int): String = when (state) {
            TelephonyManager.CALL_STATE_RINGING -> "CALL_STATE_RINGING"
            TelephonyManager.CALL_STATE_OFFHOOK -> "CALL_STATE_OFFHOOK"
            TelephonyManager.CALL_STATE_IDLE -> "CALL_STATE_IDLE"
            else -> "CALL_STATE_$state"
        }
    }
}
