package com.fitron.sellagent.audiotest.audio

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import androidx.core.content.ContextCompat
import kotlin.math.PI
import kotlin.math.max
import kotlin.math.sin
import kotlin.math.sqrt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

/**
 * "Acoustic loopback" latency estimate: a 1 kHz -> 4 kHz chirp is played through the current output route and
 * recorded with the near-end microphone at the same time. Cross-correlating the recording with the chirp gives the
 * speaker -> air -> microphone delay including the audio HAL buffers. This is NOT the network/call latency; it only
 * characterises the local acoustic path the TTS audio has to take.
 */
class LoopbackLatency(private val context: Context) {

    data class Result(
        val ok: Boolean,
        val latencyMs: Double,
        val peakCorrelation: Double,
        val noiseFloorDbfs: Double,
        val apiUsed: String,
        val error: String?,
    )

    suspend fun measure(): Result = withContext(Dispatchers.IO) {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            return@withContext Result(false, 0.0, 0.0, -120.0, API, "RECORD_AUDIO not granted")
        }
        val chirp = chirp()
        val recordSamples = SAMPLE_RATE * RECORD_SECONDS
        val minIn = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val minOut = AudioTrack.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (minIn <= 0 || minOut <= 0) return@withContext Result(false, 0.0, 0.0, -120.0, API, "buffer size query failed")
        val recorder = try {
            AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, max(minIn, SAMPLE_RATE))
        } catch (e: Exception) {
            return@withContext Result(false, 0.0, 0.0, -120.0, API, "AudioRecord: ${e.message}")
        }
        if (recorder.state != AudioRecord.STATE_INITIALIZED) {
            recorder.release()
            return@withContext Result(false, 0.0, 0.0, -120.0, API, "AudioRecord not initialised")
        }
        val track = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build())
            .setAudioFormat(AudioFormat.Builder().setSampleRate(SAMPLE_RATE).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
            .setBufferSizeInBytes(max(minOut, chirp.size * 2))
            .setTransferMode(AudioTrack.MODE_STATIC)
            .build()
        val recorded = ShortArray(recordSamples)
        try {
            if (track.state != AudioTrack.STATE_INITIALIZED && track.state != AudioTrack.STATE_NO_STATIC_DATA) {
                return@withContext Result(false, 0.0, 0.0, -120.0, API, "AudioTrack not initialised")
            }
            track.write(chirp, 0, chirp.size)
            recorder.startRecording()
            val playStartSample = SAMPLE_RATE / 2 // start the chirp 0.5 s into the recording
            coroutineScope {
                val reader = async {
                    var filled = 0
                    while (filled < recordSamples) {
                        val n = recorder.read(recorded, filled, recordSamples - filled)
                        if (n <= 0) break
                        filled += n
                    }
                    filled
                }
                delay((playStartSample * 1000L) / SAMPLE_RATE)
                track.play()
                reader.await()
            }
            runCatching { track.stop() }
            runCatching { recorder.stop() }
            val noise = noiseFloor(recorded, playStartSample)
            val (lag, peak) = bestLag(recorded, chirp, playStartSample)
            val latency = (lag - playStartSample) * 1000.0 / SAMPLE_RATE
            val ok = peak > 0.15 && latency >= 0 && latency < 1500
            Result(ok, latency, peak, noise, API, if (ok) null else "weak correlation (%.2f); raise media volume and reduce room noise".format(peak))
        } catch (e: Exception) {
            Result(false, 0.0, 0.0, -120.0, API, "${e.javaClass.simpleName}: ${e.message}")
        } finally {
            runCatching { track.release() }
            runCatching { recorder.release() }
        }
    }

    private fun chirp(): ShortArray {
        val n = SAMPLE_RATE * CHIRP_MS / 1000
        val out = ShortArray(n)
        val f0 = 1000.0
        val f1 = 4000.0
        val t1 = n.toDouble() / SAMPLE_RATE
        for (i in 0 until n) {
            val t = i.toDouble() / SAMPLE_RATE
            val phase = 2 * PI * (f0 * t + (f1 - f0) * t * t / (2 * t1))
            val env = sin(PI * i / n) // Hann-like envelope to avoid clicks
            out[i] = (sin(phase) * env * 0.8 * 32767).toInt().toShort()
        }
        return out
    }

    private fun noiseFloor(rec: ShortArray, upTo: Int): Double {
        var sum = 0.0
        val n = upTo.coerceAtMost(rec.size)
        for (i in 0 until n) { val v = rec[i] / 32768.0; sum += v * v }
        return MicLevelMeter.dbfs(if (n > 0) sqrt(sum / n) else 0.0)
    }

    /** Normalised cross-correlation on a decimated grid, then refined around the best coarse lag. */
    private fun bestLag(rec: ShortArray, ref: ShortArray, from: Int): Pair<Int, Double> {
        val r = DoubleArray(rec.size) { rec[it] / 32768.0 }
        val c = DoubleArray(ref.size) { ref[it] / 32768.0 }
        val refEnergy = sqrt(c.sumOf { it * it })
        val maxLag = rec.size - ref.size
        if (maxLag <= from) return from to 0.0
        var bestLag = from
        var best = 0.0
        val coarse = 8
        var lag = from
        while (lag < maxLag) {
            val v = corr(r, c, lag, 4, refEnergy)
            if (v > best) { best = v; bestLag = lag }
            lag += coarse
        }
        var fineBest = best
        var fineLag = bestLag
        for (l in (bestLag - coarse).coerceAtLeast(from)..(bestLag + coarse).coerceAtMost(maxLag - 1)) {
            val v = corr(r, c, l, 1, refEnergy)
            if (v > fineBest) { fineBest = v; fineLag = l }
        }
        return fineLag to fineBest
    }

    private fun corr(r: DoubleArray, c: DoubleArray, lag: Int, stride: Int, refEnergy: Double): Double {
        var dot = 0.0
        var e = 0.0
        var i = 0
        while (i < c.size) {
            val x = r[lag + i]
            dot += x * c[i]
            e += x * x
            i += stride
        }
        val denom = sqrt(e) * refEnergy / sqrt(stride.toDouble())
        return if (denom <= 1e-9) 0.0 else dot / denom
    }

    companion object {
        const val SAMPLE_RATE = 16_000
        const val CHIRP_MS = 150
        const val RECORD_SECONDS = 2
        const val API = "AudioTrack(USAGE_MEDIA) + AudioRecord(VOICE_RECOGNITION) cross-correlation"

        fun currentMediaVolumePercent(context: Context): Int? {
            val am = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return null
            val max = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
            return if (max > 0) am.getStreamVolume(AudioManager.STREAM_MUSIC) * 100 / max else null
        }
    }
}
