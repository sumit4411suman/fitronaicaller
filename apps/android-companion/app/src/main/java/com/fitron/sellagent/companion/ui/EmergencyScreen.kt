package com.fitron.sellagent.companion.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
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
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.ui.AppHeader
import com.fitron.sellagent.core.ui.BannerCard
import com.fitron.sellagent.core.ui.DangerButton
import com.fitron.sellagent.core.ui.KeyValueRow
import com.fitron.sellagent.core.ui.SectionCard
import com.fitron.sellagent.core.ui.Tone

@Composable
fun EmergencyScreen() {
    val context = LocalContext.current
    val core = context.core()
    val calls = (context.applicationContext as CompanionApp).calls
    val estop by core.socket.emergencyStopActive.collectAsStateWithLifecycle()
    val active by calls.active.collectAsStateWithLifecycle()
    val queue by calls.queue.collectAsStateWithLifecycle()

    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.emergency_title), stringResource(R.string.emergency_subtitle))
        DangerButton(
            stringResource(R.string.runner_emergency_stop),
            modifier = Modifier.fillMaxWidth().padding(16.dp).height(120.dp),
        ) { calls.emergencyStop("operator pressed emergency stop in companion app") }
        if (estop) BannerCard(stringResource(R.string.emergency_active_banner), Tone.Bad)
        SectionCard(stringResource(R.string.emergency_state)) {
            KeyValueRow(stringResource(R.string.emergency_latched), if (estop) stringResource(R.string.yes) else stringResource(R.string.no), if (estop) Tone.Bad else Tone.Good)
            KeyValueRow(stringResource(R.string.status_active_job), active?.callJobId?.take(12) ?: "-", if (active != null) Tone.Warn else Tone.Neutral)
            KeyValueRow(stringResource(R.string.tile_call_queue), queue.size.toString(), if (queue.isNotEmpty()) Tone.Warn else Tone.Neutral)
        }
        SectionCard(stringResource(R.string.emergency_what_title)) {
            Text(stringResource(R.string.emergency_what_text), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
