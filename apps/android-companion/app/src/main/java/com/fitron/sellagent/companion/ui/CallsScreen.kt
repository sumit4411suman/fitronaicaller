package com.fitron.sellagent.companion.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.R
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.companion.CompanionApp
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.telecom.AudioRouting
import com.fitron.sellagent.core.telecom.CallMonitor
import com.fitron.sellagent.core.telecom.SellAgentInCallService
import com.fitron.sellagent.core.ui.AppHeader
import com.fitron.sellagent.core.ui.BannerCard
import com.fitron.sellagent.core.ui.DangerButton
import com.fitron.sellagent.core.ui.GoldButton
import com.fitron.sellagent.core.ui.KeyValueRow
import com.fitron.sellagent.core.ui.LogList
import com.fitron.sellagent.core.ui.OutlineButton
import com.fitron.sellagent.core.ui.SectionCard
import com.fitron.sellagent.core.ui.Tone
import kotlinx.coroutines.delay

@Composable
fun CallsScreen() {
    val context = LocalContext.current
    val core = context.core()
    val calls = (context.applicationContext as CompanionApp).calls
    val pending by calls.pending.collectAsStateWithLifecycle()
    val active by calls.active.collectAsStateWithLifecycle()
    val hangup by calls.hangupInstruction.collectAsStateWithLifecycle()
    val events by calls.events.collectAsStateWithLifecycle()
    val estop by core.socket.emergencyStopActive.collectAsStateWithLifecycle()
    val coarse by core.callMonitor.state.collectAsStateWithLifecycle()
    val bound by SellAgentInCallService.bound.collectAsStateWithLifecycle()
    val detailed by SellAgentInCallService.lastEvent.collectAsStateWithLifecycle()
    var lastAction by rememberSaveable { mutableStateOf("") }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(pending) {
        while (pending != null) {
            now = System.currentTimeMillis()
            delay(1000)
        }
    }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.calls_title), stringResource(R.string.calls_subtitle))
        if (estop) BannerCard(stringResource(R.string.call_emergency_blocked), Tone.Bad)
        hangup?.let { msg ->
            BannerCard(msg, Tone.Bad)
            OutlineButton(stringResource(R.string.calls_hung_up), modifier = Modifier.padding(horizontal = 16.dp)) { calls.clearHangupInstruction() }
        }

        val p = pending
        if (p != null) {
            SectionCard(stringResource(R.string.calls_incoming_request)) {
                val remaining = ((p.expiresAtMs - now) / 1000).coerceAtLeast(0)
                Text(p.request.e164Number, style = MaterialTheme.typography.displaySmall, color = BrandColors.TextPrimary, fontWeight = FontWeight.Bold)
                KeyValueRow(stringResource(R.string.calls_display_name), p.request.displayName ?: "-", Tone.Neutral)
                KeyValueRow(stringResource(R.string.calls_mode), p.request.mode, Tone.Info)
                KeyValueRow(stringResource(R.string.calls_language), p.request.language, Tone.Neutral)
                KeyValueRow(stringResource(R.string.calls_requested_route), p.request.requestedRoute ?: "-", Tone.Neutral)
                KeyValueRow(stringResource(R.string.calls_expires_in), "$remaining s", if (remaining > 20) Tone.Good else Tone.Warn)
                KeyValueRow(stringResource(R.string.calls_job), p.request.callJobId.take(12), Tone.Neutral)
                Text(stringResource(R.string.calls_tap_to_dial), style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    GoldButton(stringResource(R.string.calls_dial), modifier = Modifier.weight(1f).height(56.dp), enabled = !estop) { lastAction = calls.dial() }
                    OutlineButton(stringResource(R.string.calls_decline), modifier = Modifier.weight(1f).height(56.dp)) { calls.decline("operator declined on phone") }
                }
            }
        } else if (active == null) {
            SectionCard(stringResource(R.string.calls_incoming_request)) {
                Text(stringResource(R.string.calls_none), style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)
            }
        }

        val a = active
        if (a != null) {
            SectionCard(stringResource(R.string.calls_active)) {
                KeyValueRow(stringResource(R.string.calls_job), a.callJobId.take(12), Tone.Warn)
                KeyValueRow(stringResource(R.string.calls_last_state), "${a.lastState} (${a.lastSource})", Tone.Info)
                KeyValueRow(stringResource(R.string.call_coarse), CallMonitor.describe(coarse.telephonyState), Tone.Neutral)
                KeyValueRow(stringResource(R.string.call_detailed), if (bound) (detailed?.let { SellAgentInCallService.describeState(it.telecomState) } ?: "-") else stringResource(R.string.call_not_bound), if (bound) Tone.Good else Tone.Neutral)
                KeyValueRow(stringResource(R.string.call_route), AudioRouting.currentRoute(context), Tone.Neutral)
                DangerButton(stringResource(R.string.call_end), enabled = bound, modifier = Modifier.fillMaxWidth()) { lastAction = "end: ${calls.endCall()}" }
                if (!bound) Text(stringResource(R.string.call_end_hint), style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary)
            }
        }
        if (lastAction.isNotBlank()) {
            SectionCard(stringResource(R.string.call_last_action)) { Text(lastAction, style = MaterialTheme.typography.bodySmall, color = BrandColors.TextPrimary) }
        }
        SectionCard(stringResource(R.string.calls_rules_title)) {
            Text(stringResource(R.string.calls_rules_text), style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)
        }
        SectionCard(stringResource(R.string.calls_log)) { LogList(events, maxLines = 30) }
        Text("", modifier = Modifier.padding(8.dp))
    }
}
