package com.fitron.sellagent.core.ui

/** Shared destinations that core screens can ask the hosting app to open; each app maps them to its own routes. */
enum class CoreDest { CONNECTION, PERMISSIONS, DIAGNOSTICS, BATTERY, LOGS, TROUBLESHOOTING, MIC_TEST, SPEAKER_TEST, AUDIO_ROUTE }
