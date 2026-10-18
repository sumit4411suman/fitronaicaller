package com.fitron.sellagent.audiotest.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.fitron.sellagent.R
import com.fitron.sellagent.audiotest.StepRecord
import com.fitron.sellagent.audiotest.TestPlan
import com.fitron.sellagent.audiotest.TestStep
import com.fitron.sellagent.audiotest.StepTool
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.ui.BannerCard
import com.fitron.sellagent.core.ui.DangerButton
import com.fitron.sellagent.core.ui.GoldButton
import com.fitron.sellagent.core.ui.KeyValueRow
import com.fitron.sellagent.core.ui.OutlineButton
import com.fitron.sellagent.core.ui.SectionCard
import com.fitron.sellagent.core.ui.StatusDot
import com.fitron.sellagent.core.ui.Tone
import com.fitron.sellagent.core.ui.color
import com.fitron.sellagent.core.ui.connectionLabel
import com.fitron.sellagent.protocol.AudioRoute
import com.fitron.sellagent.protocol.TestStatus
import java.util.Locale

fun statusTone(status: String): Tone = when (status) {
    TestStatus.PASS -> Tone.Good
    TestStatus.FAIL -> Tone.Bad
    TestStatus.BLOCKED -> Tone.Warn
    else -> Tone.Neutral
}

@Composable
fun statusLabel(status: String): String = when (status) {
    TestStatus.PASS -> stringResource(R.string.runner_mark_pass)
    TestStatus.FAIL -> stringResource(R.string.runner_mark_fail)
    TestStatus.BLOCKED -> stringResource(R.string.runner_mark_blocked)
    else -> stringResource(R.string.runner_mark_not_tested)
}

@Composable
fun TestRunnerScreen(vm: TestRunnerViewModel = viewModel()) {
    val context = LocalContext.current
    val core = context.core()
    val run by vm.session.run.collectAsStateWithLifecycle()
    val busy by vm.busyStep.collectAsStateWithLifecycle()
    val level by vm.liveLevel.collectAsStateWithLifecycle()
    val countdown by vm.countdown.collectAsStateWithLifecycle()
    val connection by core.socket.state.collectAsStateWithLifecycle()
    val pending by core.socket.pendingCount.collectAsStateWithLifecycle()
    val estop by core.socket.emergencyStopActive.collectAsStateWithLifecycle()
    var expanded by rememberSaveable { mutableStateOf("pairing") }
    var networkNote by rememberSaveable { mutableStateOf(core.store.networkConfigNote) }

    LazyColumn(modifier = Modifier.fillMaxSize()) {
        item {
            Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
                Text(stringResource(R.string.runner_title), style = MaterialTheme.typography.displaySmall, color = BrandColors.Gold)
                Text(stringResource(R.string.runner_subtitle), style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)
            }
            BannerCard(stringResource(R.string.runner_banner), Tone.Warn)
            SectionCard(stringResource(R.string.runner_test_id)) {
                val (label, tone) = connectionLabel(connection)
                KeyValueRow(stringResource(R.string.pairing_state), label, tone)
                KeyValueRow(stringResource(R.string.runner_test_id), run.testId ?: "-", if (run.testId != null) Tone.Good else Tone.Neutral)
                KeyValueRow(stringResource(R.string.runner_pending), pending.toString(), if (pending == 0) Tone.Good else Tone.Warn)
                if (run.testId == null) Text(stringResource(R.string.runner_no_run), style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)
                OutlinedTextField(
                    value = networkNote,
                    onValueChange = { networkNote = it; core.store.networkConfigNote = it },
                    label = { Text(stringResource(R.string.runner_network_note)) },
                    modifier = Modifier.fillMaxWidth(),
                    colors = fieldColors(),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    GoldButton(stringResource(R.string.runner_start_run), enabled = busy == null) { vm.session.startRun() }
                }
                DangerButton(stringResource(R.string.runner_emergency_stop), modifier = Modifier.fillMaxWidth().height(56.dp)) {
                    vm.session.emergencyStop("operator pressed emergency stop in diagnostic app")
                }
                Text(stringResource(R.string.runner_emergency_hint), style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary)
                if (estop) KeyValueRow("safety.emergency_stop", stringResource(R.string.call_emergency_blocked), Tone.Bad)
            }
        }
        items(TestPlan.steps, key = { it.step }) { step ->
            val record = run.records.firstOrNull { it.step == step.step } ?: StepRecord(step.step)
            StepCard(
                step = step,
                record = record,
                expanded = expanded == step.step,
                enabled = run.testId != null && busy == null,
                busy = busy == step.step,
                level = if (busy == step.step) level else null,
                countdown = if (busy == step.step) countdown else null,
                onToggle = { expanded = if (expanded == step.step) "" else step.step },
                vm = vm,
            )
        }
        item { Spacer(Modifier.height(24.dp)) }
    }
}

@Composable
private fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = BrandColors.Gold,
    unfocusedBorderColor = BrandColors.SurfaceBorder,
    focusedLabelColor = BrandColors.Gold,
    unfocusedLabelColor = BrandColors.TextSecondary,
    cursorColor = BrandColors.Gold,
    focusedTextColor = BrandColors.TextPrimary,
    unfocusedTextColor = BrandColors.TextPrimary,
)

@Composable
private fun StepCard(
    step: TestStep,
    record: StepRecord,
    expanded: Boolean,
    enabled: Boolean,
    busy: Boolean,
    level: Double?,
    countdown: Int?,
    onToggle: () -> Unit,
    vm: TestRunnerViewModel,
) {
    val index = TestPlan.steps.indexOf(step) + 1
    SectionCard("$index. ${stringResource(step.title)}", modifier = Modifier.clickable(onClick = onToggle)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            StatusDot(statusTone(record.status))
            Spacer(Modifier.width(8.dp))
            Text(statusLabel(record.status), color = statusTone(record.status).color(), fontWeight = FontWeight.Medium, style = MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.width(12.dp))
            Text("${stringResource(R.string.runner_direction)}: ${step.direction}", style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary)
            if (record.sent) {
                Spacer(Modifier.width(12.dp))
                Text(stringResource(R.string.runner_sent), style = MaterialTheme.typography.labelSmall, color = BrandColors.Success)
            }
        }
        if (!expanded) return@SectionCard
        Text(stringResource(step.instruction), style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)

        ToolControls(step, enabled, vm)

        if (busy) {
            LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = BrandColors.Gold, trackColor = BrandColors.SurfaceBorder)
            Text(stringResource(R.string.runner_busy), style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary)
            if (level != null) KeyValueRow(stringResource(R.string.runner_live_level), "%.1f dBFS".format(Locale.ROOT, level), Tone.Info)
            if (countdown != null) KeyValueRow(stringResource(R.string.runner_countdown), countdown.toString(), Tone.Info)
            OutlineButton(stringResource(R.string.cancel)) { vm.cancelMeasurement() }
        }

        if (record.apiUsed != null) KeyValueRow("api_used", record.apiUsed, Tone.Neutral)
        record.metrics.forEach { (k, v) -> KeyValueRow(k, "%.2f".format(Locale.ROOT, v), Tone.Info) }
        record.evidence.filterKeys { it != "operator_observation" }.forEach { (k, v) ->
            Text("$k: $v", style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary)
        }
        if (record.errorMessage != null) KeyValueRow("error", record.errorMessage, Tone.Bad)

        var observation by rememberSaveable(record.step) { mutableStateOf(record.observation) }
        OutlinedTextField(
            value = observation,
            onValueChange = { observation = it; vm.session.setObservation(step.step, it) },
            label = { Text(stringResource(R.string.runner_observation)) },
            modifier = Modifier.fillMaxWidth(),
            minLines = 2,
            colors = fieldColors(),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            GoldButton(stringResource(R.string.runner_mark_pass), enabled = enabled, modifier = Modifier.weight(1f)) { vm.session.finish(step.step, TestStatus.PASS) }
            DangerButton(stringResource(R.string.runner_mark_fail), enabled = enabled, modifier = Modifier.weight(1f)) { vm.session.finish(step.step, TestStatus.FAIL, errorMessage = record.observation.ifBlank { "operator marked fail" }) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            OutlineButton(stringResource(R.string.runner_mark_blocked), enabled = enabled, modifier = Modifier.weight(1f)) { vm.session.finish(step.step, TestStatus.BLOCKED, errorMessage = record.observation.ifBlank { "blocked: API not available to a normal app" }) }
            OutlineButton(stringResource(R.string.runner_mark_not_tested), enabled = enabled, modifier = Modifier.weight(1f)) { vm.session.finish(step.step, TestStatus.NOT_TESTED) }
        }
    }
}

@Composable
private fun ToolControls(step: TestStep, enabled: Boolean, vm: TestRunnerViewModel) {
    val id = step.step
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        when (step.tool) {
            StepTool.NONE -> Unit
            StepTool.CONNECTION -> OutlineButton(stringResource(R.string.tool_check_connection), enabled = enabled) { vm.connectionEvidence(id) }
            StepTool.CALL_STATE -> OutlineButton(stringResource(R.string.tool_snapshot_states), enabled = enabled) { vm.callStateEvidence(id) }
            StepTool.DIAL -> {
                Text(stringResource(R.string.tool_dial_hint), style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary)
                OutlineButton(stringResource(R.string.tool_record_dial), enabled = enabled) { vm.dialEvidence(id) }
            }
            StepTool.REMOTE_CAPTURE -> {
                OutlineButton(stringResource(R.string.tool_probe_remote), enabled = enabled) { vm.remoteCaptureProbe(id) }
                Text(stringResource(R.string.runner_mic_label), style = MaterialTheme.typography.labelSmall, color = BrandColors.Warning)
                OutlineButton(stringResource(R.string.tool_mic_meter), enabled = enabled) { vm.micMeter(id) }
            }
            StepTool.TTS -> OutlineButton(stringResource(R.string.tool_tts_both), enabled = enabled) { vm.tts(id, hindi = true, english = true) }
            StepTool.TWO_WAY -> {
                Text(stringResource(R.string.runner_mic_label), style = MaterialTheme.typography.labelSmall, color = BrandColors.Warning)
                OutlineButton(stringResource(R.string.tool_two_way), enabled = enabled) { vm.twoWay(id) }
            }
            StepTool.ROUTE_EARPIECE -> RouteButtons(id, AudioRoute.EARPIECE, enabled, vm)
            StepTool.ROUTE_SPEAKER -> RouteButtons(id, AudioRoute.SPEAKER, enabled, vm)
            StepTool.ROUTE_BLUETOOTH -> RouteButtons(id, AudioRoute.BLUETOOTH, enabled, vm)
            StepTool.ROUTE_WIRED -> RouteButtons(id, AudioRoute.WIRED_HEADSET, enabled, vm)
            StepTool.LOOPBACK -> OutlineButton(stringResource(R.string.tool_loopback), enabled = enabled) { vm.loopback(id) }
            StepTool.SCREEN_LOCK -> OutlineButton(stringResource(R.string.tool_screen_lock), enabled = enabled) { vm.screenLockTest(id) }
            StepTool.WIFI_DROP -> OutlineButton(stringResource(R.string.tool_wifi_snapshot), enabled = enabled) { vm.wifiEvidence(id) }
            StepTool.TTS_HINDI -> OutlineButton(stringResource(R.string.tool_tts_hindi), enabled = enabled) { vm.tts(id, hindi = true, english = false) }
            StepTool.TTS_ENGLISH -> OutlineButton(stringResource(R.string.tool_tts_english), enabled = enabled) { vm.tts(id, hindi = false, english = true) }
            StepTool.VOWIFI -> {
                Text(stringResource(R.string.tool_vowifi_hint), style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary)
                OutlineButton(stringResource(R.string.tool_vowifi_snapshot), enabled = enabled) { vm.vowifiEvidence(id) }
            }
        }
    }
}

@Composable
private fun RouteButtons(id: String, route: String, enabled: Boolean, vm: TestRunnerViewModel) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlineButton("${stringResource(R.string.tool_route)}: $route", enabled = enabled) { vm.switchRoute(id, route) }
        OutlineButton(stringResource(R.string.tool_route_read), enabled = enabled) { vm.readRoute(id) }
    }
}
