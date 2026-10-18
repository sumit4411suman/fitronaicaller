package com.fitron.sellagent.core.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import kotlin.math.PI
import kotlin.math.sin
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Plays a short 1 kHz tone through the current output and reports whether AudioTrack accepted it. */
object SpeakerTest {
    data class Result(val ok: Boolean, val apiUsed: String, val detail: String)

    suspend fun play(durationMs: Int = 600, voiceUsage: Boolean = false): Result = withContext(Dispatchers.IO) {
        val rate = 16_000
        val n = rate * durationMs / 1000
        val pcm = ShortArray(n) { i -> (sin(2 * PI * 1000.0 * i / rate) * sin(PI * i / n) * 0.6 * 32767).toInt().toShort() }
        val usage = if (voiceUsage) AudioAttributes.USAGE_VOICE_COMMUNICATION else AudioAttributes.USAGE_MEDIA
        val api = "AudioTrack(${if (voiceUsage) "USAGE_VOICE_COMMUNICATION" else "USAGE_MEDIA"})"
        val track = try {
            AudioTrack.Builder()
                .setAudioAttributes(AudioAttributes.Builder().setUsage(usage).setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build())
                .setAudioFormat(AudioFormat.Builder().setSampleRate(rate).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                .setBufferSizeInBytes(n * 2)
                .setTransferMode(AudioTrack.MODE_STATIC)
                .build()
        } catch (e: Exception) {
            return@withContext Result(false, api, "${e.javaClass.simpleName}: ${e.message}")
        }
        try {
            val written = track.write(pcm, 0, pcm.size)
            if (written <= 0) return@withContext Result(false, api, "write returned $written")
            track.play()
            Thread.sleep(durationMs.toLong() + 100)
            track.stop()
            Result(true, api, "played ${durationMs} ms tone, routed by the platform to the current output")
        } catch (e: Exception) {
            Result(false, api, "${e.javaClass.simpleName}: ${e.message}")
        } finally {
            runCatching { track.release() }
        }
    }
}
