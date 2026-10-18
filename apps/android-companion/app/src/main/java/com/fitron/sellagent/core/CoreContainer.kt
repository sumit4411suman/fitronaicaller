package com.fitron.sellagent.core

import android.app.Application
import android.content.Context
import com.fitron.sellagent.core.caps.CapabilityProbe
import com.fitron.sellagent.core.net.DeviceSocket
import com.fitron.sellagent.core.net.OutboxQueue
import com.fitron.sellagent.core.security.SecureStore
import com.fitron.sellagent.core.service.ConnectionForegroundService
import com.fitron.sellagent.core.telecom.CallMonitor
import com.fitron.sellagent.core.telecom.SellAgentInCallService
import com.fitron.sellagent.protocol.DeviceCapabilities
import com.fitron.sellagent.protocol.Envelope
import com.fitron.sellagent.protocol.Heartbeat
import com.fitron.sellagent.protocol.MessageType
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/** Application-scoped singletons shared by every screen. Each app's Application implements [CoreHost]. */
interface CoreHost {
    val core: CoreContainer
}

fun Context.core(): CoreContainer = (applicationContext as CoreHost).core

class CoreContainer(val app: Application) {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    val store = SecureStore(app)
    val uiPrefs = UiPrefs(app)
    val outbox = OutboxQueue(File(app.filesDir, "outbox.jsonl"))
    val probe = CapabilityProbe(app)
    val callMonitor = CallMonitor(app)
    val socket = DeviceSocket(store, outbox, scope) { heartbeat() }

    /** Capability flags derived only from verified runtime facts (see CapabilityProbe). */
    fun capabilities(notes: String? = null): DeviceCapabilities = probe.capabilities(
        telephonyCallbackRegistered = callMonitor.registered.value,
        inCallServiceBound = SellAgentInCallService.bound.value,
        foregroundServiceVerified = ConnectionForegroundService.running.value,
        notes = notes,
    )

    val inCall: Boolean
        get() = callMonitor.inCall || SellAgentInCallService.activeCall() != null

    fun heartbeat(): Heartbeat? {
        val pairing = store.pairing.value ?: return null
        return Heartbeat(
            deviceId = pairing.deviceId,
            batteryPercent = AppInfo.batteryPercent(app),
            network = AppInfo.networkKind(app),
            wifiCallingActive = probe.wifiCallingActive(),
            inCall = inCall,
            capabilities = capabilities(),
        )
    }

    fun sendCapabilities() {
        socket.send(Envelope.of(MessageType.CAPABILITIES, capabilities(), DeviceCapabilities.serializer()), durable = true)
    }

    /** Start background machinery: telephony listener (if permitted) and the socket loop. Idempotent. */
    fun startAll() {
        callMonitor.start()
        socket.start()
    }
}
