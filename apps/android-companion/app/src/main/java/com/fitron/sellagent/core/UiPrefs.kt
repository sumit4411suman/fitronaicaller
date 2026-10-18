package com.fitron.sellagent.core

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/** Non-secret UI preferences (onboarding, queue pause, local call notes). Secrets live in SecureStore. */
class UiPrefs(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("sellagent_ui", Context.MODE_PRIVATE)

    private val _onboardingDone = MutableStateFlow(prefs.getBoolean(KEY_ONBOARDING, false))
    val onboardingDone: StateFlow<Boolean> = _onboardingDone

    private val _queuePaused = MutableStateFlow(prefs.getBoolean(KEY_QUEUE_PAUSED, false))
    val queuePaused: StateFlow<Boolean> = _queuePaused

    fun setOnboardingDone(done: Boolean) {
        prefs.edit().putBoolean(KEY_ONBOARDING, done).apply()
        _onboardingDone.value = done
    }

    fun setQueuePaused(paused: Boolean) {
        prefs.edit().putBoolean(KEY_QUEUE_PAUSED, paused).apply()
        _queuePaused.value = paused
    }

    /** Operator notes per call job. They stay on this phone; nothing in protocol 1.0 carries them to the PC. */
    fun note(callJobId: String): String = prefs.getString(NOTE_PREFIX + callJobId, "") ?: ""

    fun setNote(callJobId: String, text: String) {
        prefs.edit().putString(NOTE_PREFIX + callJobId, text.take(2000)).apply()
    }

    private companion object {
        const val KEY_ONBOARDING = "onboarding_done"
        const val KEY_QUEUE_PAUSED = "queue_paused"
        const val NOTE_PREFIX = "note_"
    }
}
