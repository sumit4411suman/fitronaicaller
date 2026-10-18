package com.fitron.sellagent.audiotest

import android.app.Application
import com.fitron.sellagent.core.CoreContainer
import com.fitron.sellagent.core.CoreHost
import com.fitron.sellagent.core.telecom.SellAgentInCallService
import com.fitron.sellagent.protocol.MessageType
import kotlinx.coroutines.launch

/**
 * Audio Feasibility Test app. It never places campaign calls: any call.request from the backend is refused with an
 * error envelope. Emergency stop from the PC ends an active call when our InCallService is bound.
 */
class DiagnosticApp : Application(), CoreHost {
    override lateinit var core: CoreContainer
        private set
    lateinit var session: TestSession
        private set

    override fun onCreate() {
        super.onCreate()
        core = CoreContainer(this)
        session = TestSession(this, core)
        core.startAll()
        core.scope.launch {
            core.socket.inbound.collect { env ->
                when (env.type) {
                    MessageType.CALL_REQUEST -> core.socket.sendError(
                        env.messageId,
                        "diagnostic_app",
                        "diagnostic app does not place campaign calls; pair the Companion app instead",
                    )
                    MessageType.CALL_CANCEL -> core.socket.sendError(env.messageId, "diagnostic_app", "diagnostic app has no campaign calls to cancel")
                    MessageType.EMERGENCY_STOP -> {
                        val ended = SellAgentInCallService.endActiveCall()
                        session.note("emergency_stop received from PC; call ended via InCallService=$ended")
                    }
                    else -> Unit
                }
            }
        }
    }
}
