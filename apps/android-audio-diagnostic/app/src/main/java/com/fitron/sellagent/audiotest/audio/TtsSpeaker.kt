package com.fitron.sellagent.audiotest.audio

import android.content.Context
import android.media.AudioAttributes
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import java.util.Locale
import java.util.UUID
import kotlin.coroutines.resume
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Speaks fixed test phrases through android.speech.tts.TextToSpeech with USAGE_VOICE_COMMUNICATION audio attributes,
 * so that during an active call the audio follows the call's route (earpiece/speaker/BT). The far end hears it only
 * acoustically (speakerphone picked up by the phone's microphone); nothing is injected into the uplink.
 */
class TtsSpeaker(private val context: Context) {

    data class Outcome(
        val ok: Boolean,
        val engine: String?,
        val languageResult: String,
        val spoken: Int,
        val apiUsed: String,
        val error: String?,
        val totalMs: Long,
    )

    suspend fun speak(locale: Locale, phrases: List<String>): Outcome {
        val started = System.currentTimeMillis()
        val tts = initEngine() ?: return Outcome(false, null, "n/a", 0, API, "TextToSpeech init failed or timed out", 0)
        try {
            val lang = tts.setLanguage(locale)
            val langLabel = when (lang) {
                TextToSpeech.LANG_AVAILABLE -> "LANG_AVAILABLE"
                TextToSpeech.LANG_COUNTRY_AVAILABLE -> "LANG_COUNTRY_AVAILABLE"
                TextToSpeech.LANG_COUNTRY_VAR_AVAILABLE -> "LANG_COUNTRY_VAR_AVAILABLE"
                TextToSpeech.LANG_MISSING_DATA -> "LANG_MISSING_DATA"
                TextToSpeech.LANG_NOT_SUPPORTED -> "LANG_NOT_SUPPORTED"
                else -> "result_$lang"
            }
            if (lang == TextToSpeech.LANG_MISSING_DATA || lang == TextToSpeech.LANG_NOT_SUPPORTED) {
                return Outcome(false, tts.defaultEngine, langLabel, 0, API, "voice data for $locale missing; install it in Settings > Text-to-speech", System.currentTimeMillis() - started)
            }
            tts.setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
            var spoken = 0
            for (phrase in phrases) {
                val done = speakOne(tts, phrase) ?: return Outcome(false, tts.defaultEngine, langLabel, spoken, API, "utterance timed out", System.currentTimeMillis() - started)
                if (!done) return Outcome(false, tts.defaultEngine, langLabel, spoken, API, "utterance error", System.currentTimeMillis() - started)
                spoken++
            }
            return Outcome(true, tts.defaultEngine, langLabel, spoken, API, null, System.currentTimeMillis() - started)
        } finally {
            runCatching { tts.stop(); tts.shutdown() }
        }
    }

    private suspend fun initEngine(): TextToSpeech? = withTimeoutOrNull(8_000) {
        suspendCancellableCoroutine { cont ->
            var engine: TextToSpeech? = null
            engine = TextToSpeech(context) { status ->
                if (cont.isActive) cont.resume(if (status == TextToSpeech.SUCCESS) engine else null)
            }
        }
    }

    /** Returns true on done, false on error, null on timeout. */
    private suspend fun speakOne(tts: TextToSpeech, phrase: String): Boolean? = withTimeoutOrNull(30_000) {
        suspendCancellableCoroutine { cont ->
            val id = UUID.randomUUID().toString()
            tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) = Unit
                override fun onDone(utteranceId: String?) {
                    if (utteranceId == id && cont.isActive) cont.resume(true)
                }

                @Deprecated("Deprecated in Java")
                override fun onError(utteranceId: String?) {
                    if (utteranceId == id && cont.isActive) cont.resume(false)
                }

                override fun onError(utteranceId: String?, errorCode: Int) {
                    if (utteranceId == id && cont.isActive) cont.resume(false)
                }
            })
            val params = Bundle()
            params.putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, 1.0f)
            val r = tts.speak(phrase, TextToSpeech.QUEUE_FLUSH, params, id)
            if (r != TextToSpeech.SUCCESS && cont.isActive) cont.resume(false)
        }
    }

    companion object {
        const val API = "TextToSpeech.speak(USAGE_VOICE_COMMUNICATION)"
        val HINDI: Locale = Locale("hi", "IN")
        val ENGLISH_INDIA: Locale = Locale("en", "IN")
    }
}
