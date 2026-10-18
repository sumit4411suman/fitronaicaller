package com.fitron.sellagent.core.ui

import android.Manifest
import android.content.Context
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.media.MediaRecorder
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.R
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.core.audio.MicLevelMeter
import com.fitron.sellagent.core.audio.SpeakerTest
import com.fitron.sellagent.core.audio.TtsSpeaker
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.log.AppLog
import com.fitron.sellagent.core.telecom.AudioRouting
import com.fitron.sellagent.core.telecom.SellAgentInCallService
import com.fitron.sellagent.protocol.AudioRoute
import java.util.Locale
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/** Microphone test: 3 s AudioRecord(VOICE_COMMUNICATION), live and final RMS/peak dBFS (near-end only). */
@Composable
fun MicTestScreen() {
    val context = LocalContext.current
    val core = context.core()
    val scope = rememberCoroutineScope()
    var tick by remember { mutableIntStateOf(0) }
    val granted = remember(tick) { core.probe.granted(Manifest.permission.RECORD_AUDIO) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { tick++ }
    var running by remember { mutableStateOf(false) }
    var live by remember { mutableStateOf<Double?>(null) }
    var result by remember { mutableStateOf<MicLevelMeter.Result?>(null) }
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.mic_test_title), stringResource(R.string.runner_mic_label))
        SectionCard {
            if (!granted) {
                KeyValueRow("RECORD_AUDIO", stringResource(R.string.not_granted), Tone.Bad)
                GoldButton(stringResource(R.string.request)) { launcher.launch(Manifest.permission.RECORD_AUDIO) }
            } else {
                MutedText(stringResource(R.string.mic_test_help))
                GoldButton(stringResource(R.string.mic_test_run), enabled = !running, modifier = Modifier.fillMaxWidth()) {
                    running = true
                    scope.launch {
                        try {
                            val r = MicLevelMeter(context).measure(MediaRecorder.AudioSource.VOICE_COMMUNICATION, 3) { live = it }
                            result = r
                            AppLog.i("mic_test", if (r.ok) "rms %.1f dBFS peak %.1f dBFS".format(Locale.ROOT, r.rmsDbfs, r.peakDbfs) else "failed: ${r.error}")
                        } finally {
                            running = false
                            live = null
                        }
                    }
                }
            }
            if (running) {
                val lvl = live ?: -120.0
                LinearProgressIndicator(progress = { ((lvl + 90.0) / 90.0).toFloat().coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth(), color = BrandColors.Gold, trackColor = MaterialTheme.colorScheme.outline)
                KeyValueRow(stringResource(R.string.runner_live_level), "%.1f dBFS".format(Locale.ROOT, lvl), Tone.Info)
            }
            result?.let { r ->
                if (r.ok) {
                    KeyValueRow("RMS", "%.1f dBFS".format(Locale.ROOT, r.rmsDbfs), if (r.rmsDbfs > -60) Tone.Good else Tone.Warn)
                    KeyValueRow("Peak", "%.1f dBFS".format(Locale.ROOT, r.peakDbfs), if (r.peakDbfs > -3) Tone.Warn else Tone.Neutral)
                    KeyValueRow("api_used", r.apiUsed, Tone.Neutral)
                    if (r.rmsDbfs <= -60) MutedText(stringResource(R.string.mic_test_quiet))
                    if (r.peakDbfs > -3) MutedText(stringResource(R.string.mic_test_clipping))
                } else {
                    KeyValueRow(stringResource(R.string.diag_failed), r.error ?: "-", Tone.Bad)
                }
            }
        }
    }
}

/** Speaker test: 1 kHz tone, then one Hindi and one English TTS phrase, then the operator answers "Did you hear it?". */
@Composable
fun SpeakerTestScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var running by remember { mutableStateOf(false) }
    var lines by remember { mutableStateOf(listOf<Pair<String, Tone>>()) }
    var askHeard by remember { mutableStateOf(false) }
    var heard by remember { mutableStateOf<Boolean?>(null) }
    var job by remember { mutableStateOf<Job?>(null) }
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.speaker_test_title), stringResource(R.string.speaker_test_subtitle))
        SectionCard {
            MutedText(stringResource(R.string.speaker_test_help))
            GoldButton(stringResource(R.string.speaker_test_run), enabled = !running, modifier = Modifier.fillMaxWidth()) {
                running = true
                heard = null
                askHeard = false
                lines = emptyList()
                job = scope.launch {
                    try {
                        val tone = SpeakerTest.play(durationMs = 800)
                        lines = lines + ("1 kHz: ${if (tone.ok) "played" else tone.detail} (${tone.apiUsed})" to if (tone.ok) Tone.Good else Tone.Bad)
                        val tts = TtsSpeaker(context)
                        val hi = tts.speak(TtsSpeaker.HINDI, listOf(SPEAKER_PHRASE_HI))
                        lines = lines + ("TTS hi-IN: ${if (hi.ok) "spoken" else hi.error} [${hi.languageResult}]" to if (hi.ok) Tone.Good else Tone.Bad)
                        val en = tts.speak(TtsSpeaker.ENGLISH_INDIA, listOf(SPEAKER_PHRASE_EN))
                        lines = lines + ("TTS en-IN: ${if (en.ok) "spoken" else en.error} [${en.languageResult}]" to if (en.ok) Tone.Good else Tone.Bad)
                        AppLog.i("speaker_test", lines.joinToString(" | ") { it.first })
                        askHeard = true
                    } finally {
                        running = false
                    }
                }
            }
            if (running) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = BrandColors.Gold, trackColor = MaterialTheme.colorScheme.outline)
                OutlineButton(stringResource(R.string.cancel)) { job?.cancel() }
            }
            lines.forEach { (t, tone) -> KeyValueRow(t, "", tone) }
            KeyValueRow(stringResource(R.string.call_route), AudioRouting.currentRoute(context), Tone.Neutral)
            if (askHeard) {
                Text(stringResource(R.string.speaker_test_question), style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurface)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    GoldButton(stringResource(R.string.yes)) { heard = true; askHeard = false; AppLog.i("speaker_test", "operator heard the test audio: yes") }
                    OutlineButton(stringResource(R.string.no)) { heard = false; askHeard = false; AppLog.w("speaker_test", "operator heard the test audio: no") }
                }
            }
            heard?.let { h -> StatusChip(if (h) stringResource(R.string.speaker_test_heard) else stringResource(R.string.speaker_test_not_heard), if (h) Tone.Good else Tone.Bad) }
        }
    }
}

/** Audio route diagnostics: current route, platform-reported endpoints, and route switching with the API used. */
@Composable
fun AudioRouteScreen() {
    val context = LocalContext.current
    var tick by remember { mutableIntStateOf(0) }
    val bound by SellAgentInCallService.bound.collectAsStateWithLifecycle()
    val supported by SellAgentInCallService.supportedRoutes.collectAsStateWithLifecycle()
    val icsRoute by SellAgentInCallService.audioRoute.collectAsStateWithLifecycle()
    var lastAction by remember { mutableStateOf("") }
    val am = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
    val outputs = remember(tick) { am?.getDevices(AudioManager.GET_DEVICES_OUTPUTS)?.toList().orEmpty() }
    val comm = remember(tick) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) am?.availableCommunicationDevices.orEmpty() else emptyList()
    }
    val current = remember(tick, icsRoute) { AudioRouting.currentRoute(context) }
    val commDevice = remember(tick) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) runCatching { am?.communicationDevice }.getOrNull() else null
    }
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.route_title), stringResource(R.string.route_subtitle))
        SectionCard(stringResource(R.string.route_current)) {
            KeyValueRow(stringResource(R.string.call_route), current, Tone.Info)
            KeyValueRow("AudioManager.mode", am?.mode?.let { modeName(it) } ?: "-", Tone.Neutral)
            KeyValueRow("communicationDevice", commDevice?.let { "${typeName(it.type)} · ${it.productName}" } ?: "-", Tone.Neutral)
            KeyValueRow("InCallService", if (bound) stringResource(R.string.yes) else stringResource(R.string.no), if (bound) Tone.Good else Tone.Neutral)
            if (bound) KeyValueRow(stringResource(R.string.route_supported), supported.joinToString().ifBlank { "-" }, Tone.Neutral)
        }
        SectionCard(stringResource(R.string.route_endpoints)) {
            if (comm.isNotEmpty()) {
                MutedText("AudioManager.getAvailableCommunicationDevices()")
                comm.forEach { d -> KeyValueRow(typeName(d.type), d.productName.toString(), Tone.Neutral) }
            }
            MutedText("AudioManager.getDevices(GET_DEVICES_OUTPUTS)")
            outputs.forEach { d -> KeyValueRow(typeName(d.type), d.productName.toString(), Tone.Neutral) }
            if (outputs.isEmpty()) MutedText("-")
        }
        SectionCard(stringResource(R.string.call_routes_switch)) {
            MutedText(stringResource(R.string.route_switch_help))
            listOf(listOf(AudioRoute.EARPIECE, AudioRoute.SPEAKER), listOf(AudioRoute.BLUETOOTH, AudioRoute.WIRED_HEADSET)).forEach { pair ->
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    pair.forEach { r ->
                        OutlineButton(r, modifier = Modifier.weight(1f)) {
                            val res = AudioRouting.setRoute(context, r)
                            lastAction = "${res.apiUsed}: ok=${res.ok} · ${res.detail}"
                            AppLog.i("route", "set $r via ${res.apiUsed} ok=${res.ok}")
                            tick++
                        }
                    }
                }
            }
            if (lastAction.isNotBlank()) MutedText(lastAction)
            OutlineButton(stringResource(R.string.ts_recheck)) { tick++ }
        }
        Text("", modifier = Modifier.padding(8.dp))
    }
}

const val SPEAKER_PHRASE_HI = "नमस्ते, यह स्पीकर परीक्षण है।"
const val SPEAKER_PHRASE_EN = "Hello, this is a speaker test."

fun typeName(type: Int): String = when (type) {
    AudioDeviceInfo.TYPE_BUILTIN_EARPIECE -> "BUILTIN_EARPIECE"
    AudioDeviceInfo.TYPE_BUILTIN_SPEAKER -> "BUILTIN_SPEAKER"
    AudioDeviceInfo.TYPE_WIRED_HEADSET -> "WIRED_HEADSET"
    AudioDeviceInfo.TYPE_WIRED_HEADPHONES -> "WIRED_HEADPHONES"
    AudioDeviceInfo.TYPE_BLUETOOTH_SCO -> "BLUETOOTH_SCO"
    AudioDeviceInfo.TYPE_BLUETOOTH_A2DP -> "BLUETOOTH_A2DP"
    AudioDeviceInfo.TYPE_USB_HEADSET -> "USB_HEADSET"
    AudioDeviceInfo.TYPE_USB_DEVICE -> "USB_DEVICE"
    AudioDeviceInfo.TYPE_TELEPHONY -> "TELEPHONY"
    AudioDeviceInfo.TYPE_HEARING_AID -> "HEARING_AID"
    else -> "TYPE_$type"
}

fun modeName(mode: Int): String = when (mode) {
    AudioManager.MODE_NORMAL -> "MODE_NORMAL"
    AudioManager.MODE_RINGTONE -> "MODE_RINGTONE"
    AudioManager.MODE_IN_CALL -> "MODE_IN_CALL"
    AudioManager.MODE_IN_COMMUNICATION -> "MODE_IN_COMMUNICATION"
    else -> "MODE_$mode"
}
