package com.fitron.sellagent.companion.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.R
import com.fitron.sellagent.companion.CompanionApp
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.ui.BannerCard
import com.fitron.sellagent.core.ui.LiveCallScreen
import com.fitron.sellagent.core.ui.OutlineButton
import com.fitron.sellagent.core.ui.Tone

@Composable
fun CompanionLiveCall(onClose: () -> Unit) {
    val context = LocalContext.current
    val core = context.core()
    val calls = (context.applicationContext as CompanionApp).calls
    val active by calls.active.collectAsStateWithLifecycle()
    val hangup by calls.hangupInstruction.collectAsStateWithLifecycle()
    val logs by calls.logs.collectAsStateWithLifecycle()
    val jobId = active?.callJobId
    val name = jobId?.let { id -> logs.firstOrNull { it.callJobId == id }?.displayName }
    var notes by rememberSaveable(jobId) { mutableStateOf(jobId?.let { core.uiPrefs.note(it) } ?: "") }
    LiveCallScreen(
        title = active?.number,
        subtitle = listOfNotNull(name, jobId?.let { "${stringResource(R.string.calls_job)} ${it.take(12)}" }).joinToString(" · ").ifBlank { null },
        notes = notes,
        onNotesChange = { notes = it; if (jobId != null) core.uiPrefs.setNote(jobId, it) },
        onEndCall = { calls.endCall() },
        onEmergencyStop = { calls.emergencyStop("operator pressed emergency stop on live call screen") },
    ) {
        hangup?.let { BannerCard(it, Tone.Bad) }
        OutlineButton(stringResource(R.string.live_back)) { onClose() }
    }
}
