package com.fitron.sellagent.audiotest.audio

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import androidx.core.content.ContextCompat
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.sqrt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext

/**
 * Near-end microphone level meter. IMPORTANT: this measures the phone's OWN microphone (what the local user says /
 * room noise), NOT the remote party's voice. Remote-party capture needs CAPTURE_AUDIO_OUTPUT, a system permission.
 */
class MicLevelMeter(private val context: Context) {

    data class Result(
        val ok: Boolean,
        val apiUsed: String,
        val peakDbfs: Double,
        val rmsDbfs: Double,
        val seconds: Double,
        val error: String?,
    )

    /** Records for [seconds] with the given AudioSource and reports RMS/peak in dBFS; calls [onLevel] periodically. */
    suspend fun measure(
        source: Int = MediaRecorder.AudioSource.VOICE_COMMUNICATION,
        seconds: Int = 5,
        onLevel: (Double) -> Unit = {},
    ): Result = withContext(Dispatchers.IO) {
        val name = sourceName(source)
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            return@withContext Result(false, "AudioRecord($name)", -120.0, -120.0, 0.0, "RECORD_AUDIO not granted")
        }
        val minBuf = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (minBuf <= 0) return@withContext Result(false, "AudioRecord($name)", -120.0, -120.0, 0.0, "getMinBufferSize=$minBuf")
        val record = try {
            AudioRecord(source, SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, max(minBuf, SAMPLE_RATE))
        } catch (e: Exception) {
            return@withContext Result(false, "AudioRecord($name)", -120.0, -120.0, 0.0, "${e.javaClass.simpleName}: ${e.message}")
        }
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            return@withContext Result(false, "AudioRecord($name)", -120.0, -120.0, 0.0, "AudioRecord not initialised for source $name (state=${record.state})")
        }
        val buf = ShortArray(SAMPLE_RATE / 10)
        var peak = 0.0
        var sumSq = 0.0
        var count = 0L
        val started = System.nanoTime()
        try {
            record.startRecording()
            if (record.recordingState != AudioRecord.RECORDSTATE_RECORDING) {
                return@withContext Result(false, "AudioRecord($name)", -120.0, -120.0, 0.0, "startRecording did not enter RECORDING state (source may be unavailable to apps)")
            }
            while ((System.nanoTime() - started) < seconds * 1_000_000_000L) {
                ensureActive()
                val n = record.read(buf, 0, buf.size)
                if (n <= 0) continue
                var frameSq = 0.0
                for (i in 0 until n) {
                    val v = buf[i] / 32768.0
                    val a = if (v < 0) -v else v
                    if (a > peak) peak = a
                    frameSq += v * v
                }
                sumSq += frameSq
                count += n
                onLevel(dbfs(sqrt(frameSq / n)))
            }
        } catch (e: Exception) {
            return@withContext Result(false, "AudioRecord($name)", dbfs(peak), if (count > 0) dbfs(sqrt(sumSq / count)) else -120.0, 0.0, "${e.javaClass.simpleName}: ${e.message}")
        } finally {
            runCatching { record.stop() }
            record.release()
        }
        val rms = if (count > 0) sqrt(sumSq / count) else 0.0
        Result(true, "AudioRecord($name)", dbfs(peak), dbfs(rms), (System.nanoTime() - started) / 1e9, null)
    }

    companion object {
        const val SAMPLE_RATE = 16_000

        fun dbfs(amplitude: Double): Double = if (amplitude <= 1e-6) -120.0 else 20 * log10(amplitude)

        fun sourceName(source: Int): String = when (source) {
            MediaRecorder.AudioSource.VOICE_COMMUNICATION -> "VOICE_COMMUNICATION"
            MediaRecorder.AudioSource.VOICE_RECOGNITION -> "VOICE_RECOGNITION"
            MediaRecorder.AudioSource.MIC -> "MIC"
            MediaRecorder.AudioSource.VOICE_CALL -> "VOICE_CALL"
            MediaRecorder.AudioSource.VOICE_DOWNLINK -> "VOICE_DOWNLINK"
            MediaRecorder.AudioSource.VOICE_UPLINK -> "VOICE_UPLINK"
            else -> "SOURCE_$source"
        }
    }
}
