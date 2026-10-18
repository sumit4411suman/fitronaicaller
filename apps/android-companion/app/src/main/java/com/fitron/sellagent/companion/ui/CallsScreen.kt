package com.fitron.sellagent.companion.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.TabRowDefaults
import androidx.compose.material3.TabRowDefaults.tabIndicatorOffset
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.R
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.companion.CallLogEntry
import com.fitron.sellagent.companion.CompanionApp
import com.fitron.sellagent.companion.PendingCall
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.ui.AppHeader
import com.fitron.sellagent.core.ui.BannerCard
import com.fitron.sellagent.core.ui.GoldButton
import com.fitron.sellagent.core.ui.KeyValueRow
import com.fitron.sellagent.core.ui.LogList
import com.fitron.sellagent.core.ui.MutedText
import com.fitron.sellagent.core.ui.OutlineButton
import com.fitron.sellagent.core.ui.SectionCard
import com.fitron.sellagent.core.ui.StatusChip
import com.fitron.sellagent.core.ui.Tone
import com.fitron.sellagent.core.ui.brandFieldColors
import com.fitron.sellagent.protocol.CallState
import java.text.DateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.delay

fun formatDuration(seconds: Long?): String = seconds?.let { String.format(Locale.ROOT, "%d:%02d", it / 60, it % 60) } ?: "-"

fun stateTone(state: String): Tone = when (state) {
    CallState.ACTIVE, CallState.OFFHOOK -> Tone.Good
    CallState.DISCONNECTED, CallState.IDLE -> Tone.Neutral
    CallState.FAILED, CallState.REJECTED -> Tone.Bad
    else -> Tone.Info
}

@Composable
fun CallsScreen() {
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var selectedJob by rememberSaveable { mutableStateOf<String?>(null) }
    Column(modifier = Modifier.fillMaxSize()) {
        AppHeader(stringResource(R.string.calls_title), stringResource(R.string.calls_subtitle))
        TabRow(
            selectedTabIndex = tab,
            containerColor = MaterialTheme.colorScheme.background,
            contentColor = MaterialTheme.colorScheme.onBackground,
            indicator = { positions -> TabRowDefaults.SecondaryIndicator(Modifier.tabIndicatorOffset(positions[tab]), color = BrandColors.Gold) },
        ) {
            listOf(R.string.tile_call_queue, R.string.tile_call_logs, R.string.calls_summary).forEachIndexed { i, label ->
                Tab(selected = tab == i, onClick = { tab = i }, text = { Text(stringResource(label)) })
            }
        }
        when (tab) {
            0 -> QueueTab()
            1 -> LogsTab { selectedJob = it; tab = 2 }
            else -> SummaryTab(selectedJob)
        }
    }
}

@Composable
private fun QueueTab() {
    val context = LocalContext.current
    val core = context.core()
    val calls = (context.applicationContext as CompanionApp).calls
    val queue by calls.queue.collectAsStateWithLifecycle()
    val active by calls.active.collectAsStateWithLifecycle()
    val paused by core.uiPrefs.queuePaused.collectAsStateWithLifecycle()
    val estop by core.socket.emergencyStopActive.collectAsStateWithLifecycle()
    val events by calls.events.collectAsStateWithLifecycle()
    var lastAction by rememberSaveable { mutableStateOf("") }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(queue.size) {
        while (queue.isNotEmpty()) {
            now = System.currentTimeMillis()
            delay(1000)
        }
    }
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        if (estop) BannerCard(stringResource(R.string.call_emergency_blocked), Tone.Bad)
        SectionCard {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(stringResource(R.string.calls_pause_queue), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurface)
                    MutedText(stringResource(R.string.calls_pause_help))
                }
                Switch(
                    checked = paused,
                    onCheckedChange = { calls.setQueuePaused(it) },
                    colors = SwitchDefaults.colors(checkedTrackColor = BrandColors.Gold, checkedThumbColor = BrandColors.OnGold),
                )
            }
            MutedText(stringResource(R.string.calls_tap_to_dial))
        }
        if (queue.isEmpty()) SectionCard { MutedText(stringResource(R.string.calls_none)) }
        queue.forEach { p -> QueueRow(p, now, enabled = !estop && active == null) { dial -> lastAction = if (dial) calls.dial(p.request.callJobId) else { calls.decline(p.request.callJobId, "operator declined on phone"); "" } } }
        if (lastAction.isNotBlank()) SectionCard(stringResource(R.string.call_last_action)) { MutedText(lastAction) }
        SectionCard(stringResource(R.string.calls_rules_title)) { MutedText(stringResource(R.string.calls_rules_text)) }
        SectionCard(stringResource(R.string.calls_log)) { LogList(events, maxLines = 20) }
    }
}

@Composable
private fun QueueRow(p: PendingCall, now: Long, enabled: Boolean, onAction: (Boolean) -> Unit) {
    SectionCard {
        val remaining = ((p.expiresAtMs - now) / 1000).coerceAtLeast(0)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(p.request.e164Number, style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Bold)
                Text(p.request.displayName ?: "-", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            StatusChip(stringResource(R.string.calls_expires_short, remaining), if (remaining > 20) Tone.Good else Tone.Warn)
        }
        KeyValueRow(stringResource(R.string.calls_mode), p.request.mode, Tone.Info)
        KeyValueRow(stringResource(R.string.calls_language), p.request.language, Tone.Neutral)
        KeyValueRow(stringResource(R.string.calls_requested_route), p.request.requestedRoute ?: "-", Tone.Neutral)
        KeyValueRow(stringResource(R.string.calls_job), p.request.callJobId.take(12), Tone.Neutral)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            GoldButton(stringResource(R.string.calls_dial), enabled = enabled, modifier = Modifier.weight(1f)) { onAction(true) }
            OutlineButton(stringResource(R.string.calls_decline), modifier = Modifier.weight(1f)) { onAction(false) }
        }
    }
}

@Composable
private fun LogsTab(onOpen: (String) -> Unit) {
    val calls = (LocalContext.current.applicationContext as CompanionApp).calls
    val logs by calls.logs.collectAsStateWithLifecycle()
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        SectionCard { MutedText(stringResource(R.string.calls_logs_help)) }
        if (logs.isEmpty()) SectionCard { MutedText(stringResource(R.string.calls_logs_empty)) }
        logs.forEach { e -> LogRow(e) { onOpen(e.callJobId) } }
        if (logs.isNotEmpty()) OutlineButton(stringResource(R.string.calls_logs_clear), modifier = Modifier.padding(16.dp)) { calls.clearLogs() }
    }
}

@Composable
private fun LogRow(e: CallLogEntry, onClick: () -> Unit) {
    SectionCard(modifier = Modifier.clickable(onClick = onClick)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(e.number, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurface)
                Text(DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(e.receivedAtMs)), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Column(horizontalAlignment = Alignment.End) {
                StatusChip(e.finalState, stateTone(e.finalState))
                Text(formatDuration(e.durationSeconds), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun SummaryTab(callJobId: String?) {
    val context = LocalContext.current
    val core = context.core()
    val calls = (context.applicationContext as CompanionApp).calls
    val logs by calls.logs.collectAsStateWithLifecycle()
    val e = logs.firstOrNull { it.callJobId == callJobId } ?: logs.firstOrNull()
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        if (e == null) {
            SectionCard { MutedText(stringResource(R.string.calls_logs_empty)) }
            return@Column
        }
        SectionCard(stringResource(R.string.calls_summary)) {
            KeyValueRow(stringResource(R.string.calls_job), e.callJobId.take(16), Tone.Neutral)
            KeyValueRow(stringResource(R.string.calls_number), e.number, Tone.Neutral)
            KeyValueRow(stringResource(R.string.calls_display_name), e.displayName ?: "-", Tone.Neutral)
            KeyValueRow(stringResource(R.string.calls_mode), stringResource(R.string.live_mode_human), Tone.Info)
            KeyValueRow(stringResource(R.string.calls_duration), formatDuration(e.durationSeconds), Tone.Neutral)
            KeyValueRow(stringResource(R.string.calls_final_state), e.finalState, stateTone(e.finalState))
        }
        SectionCard(stringResource(R.string.calls_add_note)) {
            var note by rememberSaveable(e.callJobId) { mutableStateOf(core.uiPrefs.note(e.callJobId)) }
            MutedText(stringResource(R.string.calls_note_local))
            OutlinedTextField(
                value = note,
                onValueChange = { note = it; core.uiPrefs.setNote(e.callJobId, it) },
                modifier = Modifier.fillMaxWidth(),
                minLines = 3,
                colors = brandFieldColors(),
            )
        }
        SectionCard(stringResource(R.string.calls_events)) { LogList(e.events, maxLines = 40) }
    }
}
