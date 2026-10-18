package com.fitron.sellagent.audiotest.audio

import android.content.Context
import android.media.MediaRecorder

/**
 * Honest probe of the APIs that WOULD be needed to capture the remote party's voice. On a normal (non-system) app
 * these are expected to fail: VOICE_CALL / VOICE_DOWNLINK / VOICE_UPLINK require the system permission
 * CAPTURE_AUDIO_OUTPUT. The probe records exactly what the platform returned so the report is factual.
 */
class RemoteCaptureProbe(private val context: Context) {

    data class Outcome(val attempts: Map<String, String>, val anySucceeded: Boolean)

    suspend fun run(): Outcome {
        val meter = MicLevelMeter(context)
        val attempts = LinkedHashMap<String, String>()
        var any = false
        for (src in listOf(MediaRecorder.AudioSource.VOICE_DOWNLINK, MediaRecorder.AudioSource.VOICE_CALL, MediaRecorder.AudioSource.VOICE_UPLINK)) {
            val r = meter.measure(source = src, seconds = 2)
            val name = MicLevelMeter.sourceName(src)
            attempts[name] = if (r.ok) {
                any = true
                "UNEXPECTED: recorded %.1f s, rms %.1f dBFS - verify this is really remote audio before trusting it".format(r.seconds, r.rmsDbfs)
            } else {
                "not available: ${r.error}"
            }
        }
        attempts["AudioPlaybackCapture"] = "not attempted: the API documentation excludes USAGE_VOICE_COMMUNICATION audio from capture"
        attempts["required_permission"] = "android.permission.CAPTURE_AUDIO_OUTPUT (signature|privileged) - not grantable to this app"
        return Outcome(attempts, any)
    }
}
