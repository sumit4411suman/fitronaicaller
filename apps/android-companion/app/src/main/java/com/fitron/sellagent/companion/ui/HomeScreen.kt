package com.fitron.sellagent.companion.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.R
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.companion.CompanionApp
import com.fitron.sellagent.companion.Routes
import com.fitron.sellagent.core.AppInfo
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.net.ConnectionState
import com.fitron.sellagent.core.telecom.CallMonitor
import com.fitron.sellagent.core.telecom.SellAgentInCallService
import com.fitron.sellagent.core.ui.BannerCard
import com.fitron.sellagent.core.ui.BrandHeader
import com.fitron.sellagent.core.ui.KeyValueRow
import com.fitron.sellagent.core.ui.MutedText
import com.fitron.sellagent.core.ui.RoundAction
import com.fitron.sellagent.core.ui.SectionCard
import com.fitron.sellagent.core.ui.StatusChip
import com.fitron.sellagent.core.ui.Tone
import com.fitron.sellagent.core.ui.connectionChip
import com.fitron.sellagent.core.ui.wifiCallingLabel
import com.fitron.sellagent.protocol.NetworkKind
import java.text.DateFormat
import java.util.Date

@Composable
fun HomeScreen(navigate: (String) -> Unit) {
    val context = LocalContext.current
    val core = context.core()
    val calls = (context.applicationContext as CompanionApp).calls
    val connection by core.socket.state.collectAsStateWithLifecycle()
    val lastAck by core.socket.lastHeartbeatAckAt.collectAsStateWithLifecycle()
    val estop by core.socket.emergencyStopActive.collectAsStateWithLifecycle()
    val queue by calls.queue.collectAsStateWithLifecycle()
    val active by calls.active.collectAsStateWithLifecycle()
    val hangup by calls.hangupInstruction.collectAsStateWithLifecycle()
    val wifiCall by SellAgentInCallService.wifiCallObserved.collectAsStateWithLifecycle()
    val bound by SellAgentInCallService.bound.collectAsStateWithLifecycle()
    val detailed by SellAgentInCallService.lastEvent.collectAsStateWithLifecycle()
    val coarse by core.callMonitor.state.collectAsStateWithLifecycle()
    var lastAction by rememberSaveable { mutableStateOf("") }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        BrandHeader(subtitle = stringResource(R.string.home_subtitle), action = Icons.Filled.Settings, actionDescription = stringResource(R.string.nav_settings)) {
            navigate(Routes.SETTINGS)
        }
        Row(modifier = Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val (chip, tone) = connectionChip(connection)
            StatusChip(chip, tone, modifier = Modifier.clickable { navigate(Routes.CONNECTION) })
            StatusChip(stringResource(R.string.live_mode_human), Tone.Info)
        }
        if (estop) BannerCard(stringResource(R.string.call_emergency_blocked), Tone.Bad)
        hangup?.let { BannerCard(it, Tone.Bad) }

        SectionCard(stringResource(R.string.home_ready_title)) {
            val connected = connection is ConnectionState.Connected
            val ready = connected && !estop
            StatusChip(if (ready) stringResource(R.string.home_ready) else stringResource(R.string.home_not_ready), if (ready) Tone.Good else Tone.Warn)
            val net = AppInfo.networkKind(context)
            KeyValueRow(stringResource(R.string.status_network), if (net == NetworkKind.WIFI) stringResource(R.string.home_wifi_connected) else net, if (net == NetworkKind.WIFI) Tone.Good else Tone.Warn)
            val (w, wt) = wifiCallingLabel(wifiCall)
            KeyValueRow(stringResource(R.string.call_wifi_calling), w, wt)
            KeyValueRow(stringResource(R.string.status_battery), AppInfo.batteryPercent(context)?.let { "$it %" } ?: "-", Tone.Neutral)
            KeyValueRow(stringResource(R.string.status_last_heartbeat_ack), lastAck?.let { DateFormat.getTimeInstance().format(Date(it)) } ?: "-", if (lastAck != null) Tone.Good else Tone.Neutral)
            KeyValueRow(stringResource(R.string.home_queue), queue.size.toString(), if (queue.isEmpty()) Tone.Neutral else Tone.Warn)
            Row(modifier = Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
                RoundAction(Icons.Filled.Call, stringResource(R.string.calls_dial), BrandColors.Success, enabled = queue.isNotEmpty() && active == null && !estop) {
                    lastAction = calls.dial()
                }
                RoundAction(Icons.Filled.Close, stringResource(R.string.call_end), BrandColors.EmergencyStop, enabled = bound && active != null) {
                    lastAction = "end: ${calls.endCall()}"
                }
                RoundAction(Icons.Filled.Notifications, stringResource(R.string.home_speaker), BrandColors.GoldDark, enabled = core.inCall) {
                    lastAction = calls.toggleSpeaker()
                }
            }
            if (queue.isNotEmpty()) MutedText(stringResource(R.string.home_dial_hint, queue.first().request.e164Number))
            if (lastAction.isNotBlank()) MutedText(lastAction)
        }

        val tiles = listOf(
            Triple(Icons.Filled.List, R.string.tile_call_queue, Routes.CALLS),
            Triple(Icons.Filled.Build, R.string.diag_title, Routes.DIAGNOSTICS),
            Triple(Icons.Filled.Lock, R.string.perm_title, Routes.PERMISSIONS),
            Triple(Icons.Filled.Settings, R.string.nav_settings, Routes.SETTINGS),
            Triple(Icons.Filled.Call, R.string.tile_call_logs, Routes.CALLS),
            Triple(Icons.Filled.Info, R.string.help_title, Routes.HELP),
        )
        tiles.chunked(3).forEach { row ->
            Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { (icon, label, route) -> Tile(icon, stringResource(label), Modifier.weight(1f)) { navigate(route) } }
            }
            Spacer(Modifier.height(8.dp))
        }

        SectionCard(stringResource(R.string.home_current_call)) {
            val a = active
            if (a == null && !core.inCall) {
                MutedText(stringResource(R.string.live_no_call))
            } else {
                KeyValueRow(stringResource(R.string.calls_mode), stringResource(R.string.live_mode_human), Tone.Info)
                if (a != null) KeyValueRow(stringResource(R.string.calls_job), a.callJobId.take(12), Tone.Neutral)
                KeyValueRow(stringResource(R.string.call_coarse), CallMonitor.describe(coarse.telephonyState), Tone.Neutral)
                KeyValueRow(
                    stringResource(R.string.call_detailed),
                    if (bound) (detailed?.let { SellAgentInCallService.describeState(it.telecomState) } ?: "-") else stringResource(R.string.call_not_bound),
                    if (bound) Tone.Good else Tone.Neutral,
                )
                if (a != null) com.fitron.sellagent.core.ui.GoldButton(stringResource(R.string.live_title)) { navigate(Routes.LIVE) }
            }
        }
        Spacer(Modifier.height(16.dp))
    }
}

@Composable
private fun Tile(icon: ImageVector, label: String, modifier: Modifier, onClick: () -> Unit) {
    Card(
        modifier = modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp, horizontal = 6.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(icon, contentDescription = null, tint = BrandColors.GoldDark, modifier = Modifier.size(28.dp))
            Spacer(Modifier.height(6.dp))
            Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Medium, maxLines = 2)
        }
    }
}
