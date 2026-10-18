package com.fitron.sellagent.audiotest.ui

import android.app.Application
import com.fitron.sellagent.core.audio.MicLevelMeter
import android.media.MediaRecorder
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.fitron.sellagent.audiotest.DiagnosticApp
import com.fitron.sellagent.audiotest.TestPlan
import com.fitron.sellagent.audiotest.audio.LoopbackLatency
import com.fitron.sellagent.audiotest.audio.RemoteCaptureProbe
import com.fitron.sellagent.core.audio.TtsSpeaker
import com.fitron.sellagent.core.AppInfo
import com.fitron.sellagent.core.net.ConnectionState
import com.fitron.sellagent.core.service.ConnectionForegroundService
import com.fitron.sellagent.core.telecom.AudioRouting
import com.fitron.sellagent.core.telecom.CallMonitor
import com.fitron.sellagent.core.telecom.SellAgentInCallService
import java.util.Locale
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** Runs the automatic measurements of the Test Runner; every outcome is attached to the step via TestSession.measure. */
class TestRunnerViewModel(app: Application) : AndroidViewModel(app) {
    private val diag = app as DiagnosticApp
    private val core = diag.core
    val session = diag.session

    private val _busyStep = MutableStateFlow<String?>(null)
    val busyStep: StateFlow<String?> = _busyStep

    private val _liveLevel = MutableStateFlow<Double?>(null)
    val liveLevel: StateFlow<Double?> = _liveLevel

    private val _countdown = MutableStateFlow<Int?>(null)
    val countdown: StateFlow<Int?> = _countdown

    private var job: Job? = null

    private fun runStep(step: String, block: suspend () -> Unit) {
        if (job?.isActive == true) return
        job = viewModelScope.launch {
            _busyStep.value = step
            try {
                block()
            } catch (e: Exception) {
                session.measure(step, null, emptyMap(), mapOf("exception" to "${e.javaClass.simpleName}: ${e.message}"), "measurement failed: ${e.message}")
            } finally {
                _busyStep.value = null
                _liveLevel.value = null
                _countdown.value = null
            }
        }
    }

    fun cancelMeasurement() {
        job?.cancel()
    }

    fun connectionEvidence(step: String) = runStep(step) {
        val st = core.socket.state.value
        val pairing = core.store.pairing.value
        val ev = mapOf(
            "socket_state" to st.toString().take(120),
            "backend" to (pairing?.backendName ?: "-"),
            "endpoint" to (pairing?.let { "${it.host}:${it.port}" } ?: "-"),
            "tls_pinned_sha256" to (pairing?.tlsFingerprint ?: "-"),
            "network" to AppInfo.networkKind(core.app),
            "heartbeat_acks_this_run" to session.heartbeatAcks.value.toString(),
        )
        session.measure(step, "OkHttp WebSocket + pinned X509TrustManager", emptyMap(), ev, if (st is ConnectionState.Connected) "connected" else "not connected: $st")
    }

    fun callStateEvidence(step: String) = runStep(step) {
        val coarse = core.callMonitor.state.value
        val detailed = SellAgentInCallService.lastEvent.value
        val ev = mutableMapOf(
            "telephony_callback_registered" to core.callMonitor.registered.value.toString(),
            "telephony_last_state" to CallMonitor.describe(coarse.telephonyState),
            "in_call_service_bound" to SellAgentInCallService.bound.value.toString(),
            "default_dialer" to core.probe.isDefaultDialer().toString(),
        )
        if (detailed != null) {
            ev["in_call_last_state"] = SellAgentInCallService.describeState(detailed.telecomState)
            ev["in_call_disconnect_cause"] = detailed.disconnectCause ?: "-"
        }
        val timeline = session.run.value.timeline.filter { "TelephonyCallback" in it || "InCallService" in it }.takeLast(12)
        ev["state_timeline"] = timeline.joinToString(" | ").take(900)
        val api = if (SellAgentInCallService.bound.value) "TelephonyCallback.CallStateListener + InCallService Call.Callback" else "TelephonyCallback.CallStateListener"
        session.measure(step, api, mapOf("state_events_seen" to timeline.size.toDouble()), ev, "state evidence recorded (${timeline.size} events)")
    }

    fun remoteCaptureProbe(step: String) = runStep(step) {
        val outcome = RemoteCaptureProbe(core.app).run()
        val ev = outcome.attempts.mapKeys { "probe_${it.key}" }
        session.measure(
            step,
            "AudioRecord(VOICE_DOWNLINK|VOICE_CALL|VOICE_UPLINK) probe",
            emptyMap(),
            ev + mapOf("remote_capture_possible" to outcome.anySucceeded.toString()),
            if (outcome.anySucceeded) "UNEXPECTED: a call audio source opened - verify manually" else "system-only audio sources unavailable (expected for a normal app)",
        )
    }

    fun micMeter(step: String, seconds: Int = 5) = runStep(step) {
        val r = MicLevelMeter(core.app).measure(MediaRecorder.AudioSource.VOICE_COMMUNICATION, seconds) { _liveLevel.value = it }
        val metrics = mapOf("near_end_mic_rms_dbfs" to r.rmsDbfs, "near_end_mic_peak_dbfs" to r.peakDbfs, "near_end_mic_seconds" to r.seconds)
        session.measure(
            step, r.apiUsed, metrics,
            mapOf("mic_note" to "near-end microphone, NOT remote party audio", "mic_error" to (r.error ?: "-"), "route" to AudioRouting.currentRoute(core.app)),
            "near-end mic rms %.1f dBFS peak %.1f dBFS".format(Locale.ROOT, r.rmsDbfs, r.peakDbfs), levelDbfs = r.rmsDbfs,
        )
    }

    fun tts(step: String, hindi: Boolean, english: Boolean) = runStep(step) {
        val speaker = TtsSpeaker(core.app)
        val ev = mutableMapOf<String, String>()
        val metrics = mutableMapOf<String, Double>()
        var ok = true
        if (hindi) {
            val r = speaker.speak(TtsSpeaker.HINDI, TestPlan.hindiPhrases)
            ok = ok && r.ok
            ev["tts_hi_engine"] = r.engine ?: "-"; ev["tts_hi_language"] = r.languageResult; ev["tts_hi_error"] = r.error ?: "-"
            metrics["tts_hi_phrases_spoken"] = r.spoken.toDouble(); metrics["tts_hi_total_ms"] = r.totalMs.toDouble()
        }
        if (english) {
            val r = speaker.speak(TtsSpeaker.ENGLISH_INDIA, TestPlan.englishPhrases)
            ok = ok && r.ok
            ev["tts_en_engine"] = r.engine ?: "-"; ev["tts_en_language"] = r.languageResult; ev["tts_en_error"] = r.error ?: "-"
            metrics["tts_en_phrases_spoken"] = r.spoken.toDouble(); metrics["tts_en_total_ms"] = r.totalMs.toDouble()
        }
        ev["route"] = AudioRouting.currentRoute(core.app)
        ev["in_call"] = core.inCall.toString()
        ev["path"] = "acoustic: loudspeaker -> air -> phone microphone -> uplink; no API injects audio into the call"
        session.measure(step, TtsSpeaker.API, metrics, ev, if (ok) "TTS phrases played" else "TTS problem: ${ev.values.firstOrNull { it != "-" && "error" !in it } ?: ""}")
    }

    fun twoWay(step: String) = runStep(step) {
        coroutineScope {
            val mic = async { MicLevelMeter(core.app).measure(MediaRecorder.AudioSource.VOICE_COMMUNICATION, 12) { _liveLevel.value = it } }
            val speech = async { TtsSpeaker(core.app).speak(TtsSpeaker.ENGLISH_INDIA, TestPlan.englishPhrases.take(2)) }
            val r = mic.await()
            val s = speech.await()
            session.measure(
                step, "${TtsSpeaker.API} || ${r.apiUsed}",
                mapOf("near_end_mic_rms_dbfs" to r.rmsDbfs, "tts_phrases_spoken" to s.spoken.toDouble()),
                mapOf("mic_note" to "near-end microphone, NOT remote party audio", "tts_error" to (s.error ?: "-"), "mic_error" to (r.error ?: "-"), "route" to AudioRouting.currentRoute(core.app)),
                "simultaneous TTS + mic meter finished", levelDbfs = r.rmsDbfs,
            )
        }
    }

    fun switchRoute(step: String, route: String) = runStep(step) {
        val before = AudioRouting.currentRoute(core.app)
        val r = AudioRouting.setRoute(core.app, route)
        delay(1200)
        val after = AudioRouting.currentRoute(core.app)
        session.measure(
            step, r.apiUsed, mapOf("route_switch_ok" to if (r.ok) 1.0 else 0.0),
            mapOf("route_before" to before, "route_after" to after, "route_detail" to r.detail, "in_call" to core.inCall.toString(), "in_call_service_bound" to SellAgentInCallService.bound.value.toString()),
            "route $route via ${r.apiUsed}: ok=${r.ok}, now=$after",
        )
    }

    fun readRoute(step: String) = runStep(step) {
        val now = AudioRouting.currentRoute(core.app)
        session.measure(step, if (SellAgentInCallService.bound.value) "InCallService.onCallAudioStateChanged" else "AudioManager.getCommunicationDevice", emptyMap(), mapOf("route_now" to now), "current route $now")
    }

    fun loopback(step: String) = runStep(step) {
        val r = LoopbackLatency(core.app).measure()
        session.measure(
            step, r.apiUsed,
            mapOf("acoustic_loopback_latency_ms" to r.latencyMs, "acoustic_loopback_peak_correlation" to r.peakCorrelation, "noise_floor_dbfs" to r.noiseFloorDbfs),
            mapOf("loopback_note" to "acoustic loopback (speaker->mic), not network latency", "loopback_error" to (r.error ?: "-"), "media_volume_percent" to (LoopbackLatency.currentMediaVolumePercent(core.app)?.toString() ?: "-"), "route" to AudioRouting.currentRoute(core.app)),
            "acoustic loopback %.0f ms (corr %.2f)".format(Locale.ROOT, r.latencyMs, r.peakCorrelation), latencyMs = r.latencyMs,
        )
    }

    fun screenLockTest(step: String) = runStep(step) {
        ConnectionForegroundService.start(core.app, core.app.getString(com.fitron.sellagent.R.string.step_screen_locked))
        val acks0 = session.heartbeatAcks.value
        val disc0 = session.disconnects.value
        val coarse0 = session.run.value.timeline.count { "TelephonyCallback" in it }
        for (s in 60 downTo 1) {
            _countdown.value = s
            delay(1000)
        }
        val acks = session.heartbeatAcks.value - acks0
        val disc = session.disconnects.value - disc0
        val coarse = session.run.value.timeline.count { "TelephonyCallback" in it } - coarse0
        session.measure(
            step, "ForegroundService(${ConnectionForegroundService.describeTypes(ConnectionForegroundService.typesInUse.value)}) + heartbeat",
            mapOf("heartbeat_acks_in_60s" to acks.toDouble(), "disconnects_in_60s" to disc.toDouble(), "telephony_callbacks_in_60s" to coarse.toDouble()),
            mapOf("fgs_running_after" to ConnectionForegroundService.running.value.toString(), "fgs_detail" to ConnectionForegroundService.lastDetail.value, "socket_state_after" to core.socket.state.value.toString().take(80)),
            "60 s lock test: $acks heartbeat acks, $disc disconnects, fgs=${ConnectionForegroundService.running.value}",
        )
    }

    fun wifiEvidence(step: String) = runStep(step) {
        session.measure(
            step, "OkHttp WebSocket reconnect with exponential backoff + outbox replay",
            mapOf("reconnects_this_run" to session.reconnects.value.toDouble(), "disconnects_this_run" to session.disconnects.value.toDouble(), "max_backoff_seconds" to session.maxBackoff.value.toDouble(), "unsent_results_now" to core.socket.pendingCount.value.toDouble()),
            mapOf("socket_state" to core.socket.state.value.toString().take(80), "emergency_stop_active" to core.socket.emergencyStopActive.value.toString(), "transport_log" to core.socket.log.value.takeLast(15).joinToString(" | ").take(900)),
            "reconnection evidence recorded",
        )
    }

    fun vowifiEvidence(step: String) = runStep(step) {
        session.measure(
            step, "TelephonyManager (no public VoWiFi API) + ConnectivityManager",
            emptyMap(),
            mapOf("wifi_calling_active" to "unknown - TelephonyManager.isWifiCallingAvailable is not a public API", "network" to AppInfo.networkKind(core.app), "in_call" to core.inCall.toString(), "route" to AudioRouting.currentRoute(core.app), "operator_network_note" to core.store.networkConfigNote.take(200)),
            "network evidence recorded; VoWiFi status must be read from the status bar by the operator",
        )
    }

    /** F: which call-audio permissions a normal (non-system) app can actually hold on this phone. */
    fun apiSupportEvidence(step: String) = runStep(step) {
        val ctx = core.app
        fun state(p: String) = if (androidx.core.content.ContextCompat.checkSelfPermission(ctx, p) == android.content.pm.PackageManager.PERMISSION_GRANTED) "granted" else "denied"
        val ev = linkedMapOf(
            "CAPTURE_AUDIO_OUTPUT" to state("android.permission.CAPTURE_AUDIO_OUTPUT") + " (signature|privileged: system/OEM apps only)",
            "MODIFY_PHONE_STATE" to state("android.permission.MODIFY_PHONE_STATE") + " (signature|privileged)",
            "RECORD_AUDIO" to state(android.Manifest.permission.RECORD_AUDIO) + " (near-end microphone only)",
            "CALL_PHONE" to state(android.Manifest.permission.CALL_PHONE),
            "default_dialer" to core.probe.isDefaultDialer().toString(),
            "in_call_service_bound" to SellAgentInCallService.bound.value.toString(),
            "public_api_for_remote_call_audio" to "none (InCallService exposes call control and audio ROUTE, not the audio stream)",
            "public_api_for_uplink_injection" to "none for third-party apps on a cellular/IMS call",
            "android" to AppInfo.androidVersion(), "device" to AppInfo.deviceModel(),
        )
        val privileged = ev["CAPTURE_AUDIO_OUTPUT"]!!.startsWith("granted")
        session.measure(step, "PackageManager.checkSelfPermission + RoleManager", emptyMap(), ev, if (privileged) "UNEXPECTED: privileged call-audio permission granted - verify" else "privileged call-audio permissions denied to this app (expected)")
    }

    fun dialEvidence(step: String) = runStep(step) {
        val detailed = SellAgentInCallService.lastEvent.value
        session.measure(
            step, "TelecomManager.placeCall",
            emptyMap(),
            mapOf(
                "telephony_last_state" to CallMonitor.describe(core.callMonitor.state.value.telephonyState),
                "in_call_last_state" to (detailed?.let { SellAgentInCallService.describeState(it.telecomState) } ?: "-"),
                "dial_log" to session.run.value.timeline.filter { "placeCall" in it }.takeLast(3).joinToString(" | ").take(300),
            ),
            "dial evidence recorded",
        )
    }
}
