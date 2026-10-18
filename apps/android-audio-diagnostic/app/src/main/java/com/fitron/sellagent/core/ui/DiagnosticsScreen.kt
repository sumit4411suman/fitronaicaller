package com.fitron.sellagent.core.ui

import android.Manifest
import android.media.MediaRecorder
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
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
import com.fitron.sellagent.core.audio.MicLevelMeter
import com.fitron.sellagent.core.audio.SpeakerTest
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.log.AppLog
import com.fitron.sellagent.core.power.BatteryOptimization
import com.fitron.sellagent.core.net.NetworkLatency
import com.fitron.sellagent.core.telecom.AudioRouting
import com.fitron.sellagent.core.telecom.SellAgentInCallService
import java.util.Locale
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/** One row of the Diagnostics screen; value/tone are filled only by real measurements. */
data class DiagRow(val label: String, val value: String, val tone: Tone, val detail: String? = null)

/**
 * Short local self-check (Microphone, Speaker, Wi-Fi calling, Audio route, Network latency). Nothing here is a
 * substitute for the 16-step Audio Feasibility Test; the companion uses it as a quick sanity check.
 */
@Composable
fun DiagnosticsScreen(navigate: (CoreDest) -> Unit = {}, footer: @Composable () -> Unit = {}) {
    val context = LocalContext.current
    val core = context.core()
    val scope = rememberCoroutineScope()
    val wifiCall by SellAgentInCallService.wifiCallObserved.collectAsStateWithLifecycle()
    val pairing by core.store.pairing.collectAsStateWithLifecycle()

    val notRun = stringResource(R.string.diag_not_run)
    var mic by remember { mutableStateOf(DiagRow("", notRun, Tone.Neutral)) }
    var speaker by remember { mutableStateOf(DiagRow("", notRun, Tone.Neutral)) }
    var latency by remember { mutableStateOf(DiagRow("", notRun, Tone.Neutral)) }
    var battery by remember { mutableStateOf(DiagRow("", notRun, Tone.Neutral)) }
    var running by remember { mutableStateOf(false) }
    var job by remember { mutableStateOf<Job?>(null) }
    var liveLevel by remember { mutableStateOf<Double?>(null) }

    val micGranted = core.probe.granted(Manifest.permission.RECORD_AUDIO)
    val route = AudioRouting.currentRoute(context)
    val (wifiText, wifiTone) = wifiCallingLabel(wifiCall)

    fun runAll() {
        if (running) return
        running = true
        job = scope.launch {
            try {
                val ignoring = BatteryOptimization.isIgnoring(context)
                battery = DiagRow(
                    "",
                    when (ignoring) { true -> context.getString(R.string.battery_unrestricted); false -> context.getString(R.string.battery_optimized); null -> context.getString(R.string.unknown) },
                    if (ignoring == true) Tone.Good else Tone.Warn,
                    "PowerManager.isIgnoringBatteryOptimizations",
                )
                if (!micGranted) {
                    mic = DiagRow("", context.getString(R.string.not_granted), Tone.Bad, "RECORD_AUDIO")
                } else {
                    val r = MicLevelMeter(context).measure(MediaRecorder.AudioSource.VOICE_COMMUNICATION, 3) { liveLevel = it }
                    liveLevel = null
                    mic = if (r.ok) {
                        DiagRow("", "%.1f dBFS".format(Locale.ROOT, r.rmsDbfs), if (r.rmsDbfs > -60) Tone.Good else Tone.Warn, "${r.apiUsed} · ${context.getString(R.string.runner_mic_label)}")
                    } else {
                        DiagRow("", context.getString(R.string.diag_failed), Tone.Bad, r.error)
                    }
                }
                val s = SpeakerTest.play()
                speaker = DiagRow("", if (s.ok) context.getString(R.string.diag_tone_played) else context.getString(R.string.diag_failed), if (s.ok) Tone.Good else Tone.Bad, "${s.apiUsed} · ${s.detail}")
                val p = pairing
                latency = if (p == null) {
                    DiagRow("", context.getString(R.string.conn_unpaired), Tone.Warn)
                } else {
                    val l = NetworkLatency.measure(p)
                    if (l.ok) DiagRow("", "%.0f ms".format(Locale.ROOT, l.medianMs), if (l.medianMs < 150) Tone.Good else Tone.Warn, l.detail)
                    else DiagRow("", context.getString(R.string.diag_failed), Tone.Bad, l.detail)
                }
                AppLog.i("diagnostics", "self-check mic=${mic.value} speaker=${speaker.value} latency=${latency.value} battery=${battery.value}")
            } finally {
                running = false
                liveLevel = null
            }
        }
    }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.diag_title), stringResource(R.string.diag_subtitle))
        SectionCard {
            DiagLine(stringResource(R.string.diag_microphone), mic.value, mic.tone, mic.detail)
            if (liveLevel != null) KeyValueRow(stringResource(R.string.runner_live_level), "%.1f dBFS".format(Locale.ROOT, liveLevel!!), Tone.Info)
            DiagLine(stringResource(R.string.diag_speaker), speaker.value, speaker.tone, speaker.detail)
            DiagLine(stringResource(R.string.call_wifi_calling), wifiText, wifiTone, stringResource(R.string.diag_wifi_calling_detail))
            DiagLine(stringResource(R.string.call_route), route, Tone.Neutral, if (SellAgentInCallService.bound.value) "InCallService" else "AudioManager")
            DiagLine(stringResource(R.string.diag_network_latency), latency.value, latency.tone, latency.detail)
            DiagLine(stringResource(R.string.battery_title), battery.value, battery.tone, battery.detail)
            if (running) LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = BrandColors.Gold, trackColor = MaterialTheme.colorScheme.outline)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GoldButton(stringResource(R.string.diag_run_full), enabled = !running, modifier = Modifier.weight(1f)) { runAll() }
                if (running) OutlineButton(stringResource(R.string.cancel)) { job?.cancel() }
            }
            MutedText(stringResource(R.string.diag_note))
        }
        SectionCard(stringResource(R.string.diag_tools)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlineButton(stringResource(R.string.mic_test_title), modifier = Modifier.weight(1f)) { navigate(CoreDest.MIC_TEST) }
                OutlineButton(stringResource(R.string.speaker_test_title), modifier = Modifier.weight(1f)) { navigate(CoreDest.SPEAKER_TEST) }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlineButton(stringResource(R.string.route_title), modifier = Modifier.weight(1f)) { navigate(CoreDest.AUDIO_ROUTE) }
                OutlineButton(stringResource(R.string.battery_title), modifier = Modifier.weight(1f)) { navigate(CoreDest.BATTERY) }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlineButton(stringResource(R.string.ts_title), modifier = Modifier.weight(1f)) { navigate(CoreDest.TROUBLESHOOTING) }
                OutlineButton(stringResource(R.string.logs_title), modifier = Modifier.weight(1f)) { navigate(CoreDest.LOGS) }
            }
        }
        footer()
        Text("", modifier = Modifier.padding(8.dp))
    }
}

@Composable
private fun DiagLine(label: String, value: String, tone: Tone, detail: String?) {
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Medium)
            StatusChip(value, tone)
        }
        if (!detail.isNullOrBlank()) Text(detail, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
