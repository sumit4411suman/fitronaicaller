package com.fitron.sellagent.core.ui

import android.content.Intent
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.R
import com.fitron.sellagent.core.AppInfo
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.log.AppLog
import com.fitron.sellagent.core.net.ConnectionState
import com.fitron.sellagent.core.power.BatteryOptimization
import com.fitron.sellagent.protocol.NetworkKind

/** One check result; [ok] is computed from live platform state, never assumed. */
private data class Check(val title: String, val ok: Boolean, val detail: String, val fixLabel: String?, val fix: (() -> Unit)?)

@Composable
fun TroubleshootingScreen(navigate: (CoreDest) -> Unit) {
    val context = LocalContext.current
    val core = context.core()
    var tick by remember { mutableIntStateOf(0) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { tick++ }
    val connection by core.socket.state.collectAsStateWithLifecycle()
    val lastFailure by core.socket.lastFailure.collectAsStateWithLifecycle()
    val estop by core.socket.emergencyStopActive.collectAsStateWithLifecycle()
    val pairing by core.store.pairing.collectAsStateWithLifecycle()

    val missing = remember(tick) { core.probe.runtimePermissions().filterNot { core.probe.granted(it) }.map { it.substringAfterLast('.') } }
    val dialer = remember(tick) { core.probe.isDefaultDialer() }
    val battery = remember(tick) { BatteryOptimization.isIgnoring(context) }
    val network = remember(tick) { AppInfo.networkKind(context) }
    val certProblem = lastFailure != null && core.socket.lastFailureIsCertificate
    val address = pairing?.let { "${it.host}:${it.port}" } ?: stringResource(R.string.conn_unpaired)

    val checks = listOf(
        Check(
            stringResource(R.string.ts_connection), connection is ConnectionState.Connected,
            stringResource(R.string.ts_connection_detail, address, lastFailure ?: "-"),
            stringResource(if (pairing == null) R.string.pairing_pair else R.string.pairing_reconnect),
        ) { if (pairing == null) navigate(CoreDest.CONNECTION) else core.socket.reconnectNow() },
        Check(
            stringResource(R.string.ts_certificate), !certProblem,
            if (certProblem) stringResource(R.string.ts_certificate_bad) else stringResource(R.string.ts_certificate_ok),
            if (certProblem) stringResource(R.string.ts_pair_again) else null,
        ) {
            AppLog.w("troubleshoot", "operator re-pairs after certificate mismatch")
            core.store.forgetPairing()
            navigate(CoreDest.CONNECTION)
        },
        Check(
            stringResource(R.string.ts_permissions), missing.isEmpty(),
            if (missing.isEmpty()) stringResource(R.string.ts_all_granted) else missing.joinToString(", "),
            stringResource(R.string.perm_title),
        ) { navigate(CoreDest.PERMISSIONS) },
        Check(stringResource(R.string.ts_dialer), dialer, stringResource(R.string.ts_dialer_detail), stringResource(R.string.perm_title)) { navigate(CoreDest.PERMISSIONS) },
        Check(
            stringResource(R.string.battery_title), battery == true,
            batteryLabel(battery).first, stringResource(R.string.battery_title),
        ) { navigate(CoreDest.BATTERY) },
        Check(
            stringResource(R.string.ts_wifi), network == NetworkKind.WIFI, network, stringResource(R.string.ts_open_wifi),
        ) { runCatching { context.startActivity(Intent(Settings.ACTION_WIFI_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } },
        Check(stringResource(R.string.ts_estop), !estop, if (estop) stringResource(R.string.ts_estop_on) else stringResource(R.string.ts_estop_off), null, null),
    )
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.ts_title), stringResource(R.string.ts_subtitle, checks.count { !it.ok }))
        checks.forEach { c ->
            SectionCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(c.title, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Medium)
                    StatusChip(if (c.ok) stringResource(R.string.ts_ok) else stringResource(R.string.ts_problem), if (c.ok) Tone.Good else Tone.Bad)
                }
                MutedText(c.detail)
                if (!c.ok && c.fixLabel != null && c.fix != null) GoldButton(c.fixLabel) { c.fix.invoke() }
            }
        }
        Row(modifier = Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlineButton(stringResource(R.string.ts_recheck)) { tick++ }
            OutlineButton(stringResource(R.string.logs_title)) { navigate(CoreDest.LOGS) }
        }
    }
}
