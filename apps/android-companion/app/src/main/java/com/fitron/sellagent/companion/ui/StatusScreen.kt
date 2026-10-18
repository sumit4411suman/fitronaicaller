package com.fitron.sellagent.companion.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.R
import com.fitron.sellagent.companion.CompanionApp
import com.fitron.sellagent.core.AppInfo
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.net.ConnectionState
import com.fitron.sellagent.core.service.ConnectionForegroundService
import com.fitron.sellagent.core.telecom.SellAgentInCallService
import com.fitron.sellagent.core.ui.AppHeader
import com.fitron.sellagent.core.ui.BannerCard
import com.fitron.sellagent.core.ui.GoldButton
import com.fitron.sellagent.core.ui.KeyValueRow
import com.fitron.sellagent.core.ui.LogList
import com.fitron.sellagent.core.ui.OutlineButton
import com.fitron.sellagent.core.ui.SectionCard
import com.fitron.sellagent.core.ui.Tone
import com.fitron.sellagent.core.ui.connectionLabel
import com.fitron.sellagent.core.ui.yesNo
import java.text.DateFormat
import java.util.Date

@Composable
fun StatusScreen(onPair: () -> Unit) {
    val context = LocalContext.current
    val core = context.core()
    val calls = (context.applicationContext as CompanionApp).calls
    val pairing by core.store.pairing.collectAsStateWithLifecycle()
    val connection by core.socket.state.collectAsStateWithLifecycle()
    val lastAck by core.socket.lastHeartbeatAckAt.collectAsStateWithLifecycle()
    val pendingCount by core.socket.pendingCount.collectAsStateWithLifecycle()
    val estop by core.socket.emergencyStopActive.collectAsStateWithLifecycle()
    val log by core.socket.log.collectAsStateWithLifecycle()
    val monitor by core.callMonitor.registered.collectAsStateWithLifecycle()
    val bound by SellAgentInCallService.bound.collectAsStateWithLifecycle()
    val fgs by ConnectionForegroundService.running.collectAsStateWithLifecycle()
    val active by calls.active.collectAsStateWithLifecycle()

    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.status_title), stringResource(R.string.status_subtitle))
        if (estop) BannerCard(stringResource(R.string.call_emergency_blocked), Tone.Bad)
        BannerCard(stringResource(R.string.status_mode_banner), Tone.Info)
        SectionCard(stringResource(R.string.status_connection)) {
            val (label, tone) = connectionLabel(connection)
            KeyValueRow(stringResource(R.string.pairing_state), label, tone)
            KeyValueRow(stringResource(R.string.pairing_backend), pairing?.backendName ?: "-", if (pairing != null) Tone.Good else Tone.Neutral)
            KeyValueRow(stringResource(R.string.pairing_device_id), pairing?.deviceId?.take(12) ?: "-", Tone.Neutral)
            KeyValueRow(stringResource(R.string.status_last_heartbeat_ack), lastAck?.let { DateFormat.getTimeInstance().format(Date(it)) } ?: "-", if (lastAck != null) Tone.Good else Tone.Neutral)
            KeyValueRow(stringResource(R.string.status_unsent_events), pendingCount.toString(), if (pendingCount == 0) Tone.Good else Tone.Warn)
            if (pairing == null) GoldButton(stringResource(R.string.pairing_pair)) { onPair() }
            else OutlineButton(stringResource(R.string.pairing_reconnect), enabled = connection !is ConnectionState.Connected) { core.socket.reconnectNow() }
        }
        SectionCard(stringResource(R.string.status_device)) {
            KeyValueRow(stringResource(R.string.status_battery), AppInfo.batteryPercent(context)?.let { "$it %" } ?: "-", Tone.Neutral)
            KeyValueRow(stringResource(R.string.status_network), AppInfo.networkKind(context), Tone.Neutral)
            KeyValueRow(stringResource(R.string.call_wifi_calling), stringResource(R.string.unknown_no_public_api), Tone.Neutral)
            KeyValueRow(stringResource(R.string.status_in_call), yesNo(core.inCall), if (core.inCall) Tone.Warn else Tone.Neutral)
            KeyValueRow(stringResource(R.string.status_active_job), active?.callJobId?.take(12) ?: "-", if (active != null) Tone.Warn else Tone.Neutral)
            KeyValueRow("TelephonyCallback", yesNo(monitor), if (monitor) Tone.Good else Tone.Warn)
            KeyValueRow("InCallService", yesNo(bound), if (bound) Tone.Good else Tone.Neutral)
            KeyValueRow(stringResource(R.string.perm_fgs_running), yesNo(fgs), if (fgs) Tone.Good else Tone.Neutral)
            Text(stringResource(R.string.status_heartbeat_note), style = androidx.compose.material3.MaterialTheme.typography.labelSmall, color = com.fitron.sellagent.brand.BrandColors.TextSecondary)
        }
        SectionCard(stringResource(R.string.transport_log)) { LogList(log, maxLines = 20) }
        Text("", modifier = Modifier.padding(8.dp))
    }
}
