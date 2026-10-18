package com.fitron.sellagent.companion.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.R
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.core.AppInfo
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.ui.AppHeader
import com.fitron.sellagent.core.ui.GoldButton
import com.fitron.sellagent.core.ui.KeyValueRow
import com.fitron.sellagent.core.ui.OutlineButton
import com.fitron.sellagent.core.ui.SectionCard
import com.fitron.sellagent.core.ui.Tone
import com.fitron.sellagent.protocol.PROTOCOL_VERSION

@Composable
fun SettingsScreen(onPair: () -> Unit) {
    val context = LocalContext.current
    val core = context.core()
    val pairing by core.store.pairing.collectAsStateWithLifecycle()
    val pendingCount by core.socket.pendingCount.collectAsStateWithLifecycle()

    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.settings_title), stringResource(R.string.settings_subtitle))
        SectionCard(stringResource(R.string.settings_mode)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(stringResource(R.string.settings_human_assisted), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurface)
                    Text(stringResource(R.string.settings_mode_help), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                // Human-assisted is the only working path; the toggle is fixed ON and disabled so the state is explicit.
                Switch(
                    checked = true,
                    onCheckedChange = null,
                    enabled = false,
                    colors = SwitchDefaults.colors(disabledCheckedTrackColor = BrandColors.Gold, disabledCheckedThumbColor = BrandColors.ContentSurface),
                )
            }
            KeyValueRow(stringResource(R.string.settings_autonomous), stringResource(R.string.settings_autonomous_value), Tone.Warn)
        }
        SectionCard(stringResource(R.string.settings_connection)) {
            KeyValueRow(stringResource(R.string.pairing_endpoint), pairing?.let { "${it.host}:${it.port}" } ?: "-", Tone.Neutral)
            KeyValueRow(stringResource(R.string.status_unsent_events), pendingCount.toString(), if (pendingCount == 0) Tone.Good else Tone.Warn)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlineButton(stringResource(R.string.pairing_reconnect), enabled = pairing != null) { core.socket.reconnectNow() }
                if (pairing == null) GoldButton(stringResource(R.string.pairing_pair)) { onPair() }
                else com.fitron.sellagent.core.ui.DangerOutlineButton(stringResource(R.string.pairing_disconnect)) {
                    core.store.forgetPairing()
                    core.outbox.clear()
                }
            }
            if (pairing != null) OutlineButton(stringResource(R.string.settings_open_pairing)) { onPair() }
        }
        SectionCard(stringResource(R.string.settings_about)) {
            KeyValueRow(stringResource(R.string.settings_app_version), AppInfo.appVersion(context), Tone.Neutral)
            KeyValueRow(stringResource(R.string.settings_protocol), PROTOCOL_VERSION, Tone.Neutral)
            KeyValueRow(stringResource(R.string.settings_device), AppInfo.deviceModel(), Tone.Neutral)
            KeyValueRow(stringResource(R.string.settings_android), AppInfo.androidVersion(), Tone.Neutral)
            Text(stringResource(R.string.settings_about_text), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Text("", modifier = Modifier.padding(8.dp))
    }
}
