package com.fitron.sellagent.core.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.R
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.brand.SellAgentTheme
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.telecom.AudioRouting
import com.fitron.sellagent.core.telecom.CallMonitor
import com.fitron.sellagent.core.telecom.SellAgentInCallService
import java.util.Locale
import kotlinx.coroutines.delay
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.MoreVert

/**
 * Dark live-call screen. Everything shown is observed: timer from InCallService STATE_ACTIVE (or the moment the
 * coarse state became OFFHOOK), state label from InCallService/TelephonyCallback, route from AudioRouting.
 * No transcript is shown because apps cannot access call audio. Mute/Hold/Keypad require the InCallService binding.
 */
@Composable
fun LiveCallScreen(
    title: String?,
    subtitle: String?,
    notes: String,
    onNotesChange: (String) -> Unit,
    onEndCall: () -> Unit,
    onEmergencyStop: () -> Unit,
    extra: @Composable () -> Unit = {},
) {
    val context = LocalContext.current
    val core = context.core()
    val bound by SellAgentInCallService.bound.collectAsStateWithLifecycle()
    val detailed by SellAgentInCallService.lastEvent.collectAsStateWithLifecycle()
    val activeSince by SellAgentInCallService.activeSinceMs.collectAsStateWithLifecycle()
    val muted by SellAgentInCallService.muted.collectAsStateWithLifecycle()
    val coarse by core.callMonitor.state.collectAsStateWithLifecycle()
    val wifiCall by SellAgentInCallService.wifiCallObserved.collectAsStateWithLifecycle()
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var held by rememberSaveable { mutableStateOf(false) }
    var keypad by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        while (true) {
            now = System.currentTimeMillis()
            delay(1000)
        }
    }
    val start = activeSince ?: if (coarse.telephonyState == android.telephony.TelephonyManager.CALL_STATE_OFFHOOK) coarse.atMillis else null
    val timer = start?.let {
        val s = ((now - it) / 1000).coerceAtLeast(0)
        String.format(Locale.ROOT, "%02d:%02d", s / 60, s % 60)
    } ?: "--:--"
    val stateText = if (bound && detailed != null) {
        SellAgentInCallService.describeState(detailed!!.telecomState)
    } else {
        CallMonitor.describe(coarse.telephonyState)
    }

    SellAgentTheme(dark = true) {
        Column(
            modifier = Modifier.fillMaxSize().background(BrandColors.Background).verticalScroll(rememberScrollState()).padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.live_title), style = MaterialTheme.typography.titleLarge, color = BrandColors.TextPrimary, modifier = Modifier.weight(1f))
                StatusChip(stringResource(R.string.live_mode_human), Tone.Info)
            }
            LogoMark(size = 72.dp)
            Text(title ?: stringResource(R.string.live_no_call), style = MaterialTheme.typography.titleLarge, color = BrandColors.TextPrimary, fontWeight = FontWeight.Bold)
            if (subtitle != null) Text(subtitle, style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)
            Text(timer, color = BrandColors.Gold, fontSize = 40.sp, fontWeight = FontWeight.Bold)
            StatusChip("${stringResource(R.string.live_state)}: $stateText", Tone.Good)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatusChip("${stringResource(R.string.call_route)}: ${AudioRouting.currentRoute(context)}", Tone.Neutral)
                val (w, wt) = wifiCallingLabel(wifiCall)
                StatusChip("${stringResource(R.string.call_wifi_calling)}: $w", wt)
            }

            SectionCard(stringResource(R.string.live_notes), modifier = Modifier.padding(horizontal = 0.dp)) {
                MutedText(stringResource(R.string.live_no_transcript))
                OutlinedTextField(
                    value = notes,
                    onValueChange = onNotesChange,
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 3,
                    colors = brandFieldColors(),
                )
            }

            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                RoundAction(Icons.Filled.Clear, if (muted) stringResource(R.string.live_unmute) else stringResource(R.string.live_mute), BrandColors.GoldDark, bound) {
                    SellAgentInCallService.setMutedCompat(!muted)
                }
                RoundAction(Icons.Filled.Refresh, if (held) stringResource(R.string.live_unhold) else stringResource(R.string.live_hold), BrandColors.GoldDark, bound) {
                    if (SellAgentInCallService.holdActive(!held)) held = !held
                }
                RoundAction(Icons.Filled.MoreVert, stringResource(R.string.live_keypad), BrandColors.GoldDark, bound) { keypad = !keypad }
            }
            if (!bound) MutedText(stringResource(R.string.live_controls_disabled))
            if (keypad && bound) {
                listOf("123", "456", "789", "*0#").forEach { rowKeys ->
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        rowKeys.forEach { k -> OutlineButton(k.toString()) { SellAgentInCallService.playDtmf(k) } }
                    }
                }
            }
            extra()
            DangerButton(stringResource(R.string.live_end_call), enabled = bound, modifier = Modifier.fillMaxWidth().height(56.dp)) { onEndCall() }
            DangerOutlineButton(stringResource(R.string.live_emergency), modifier = Modifier.fillMaxWidth()) { onEmergencyStop() }
            Spacer(Modifier.height(12.dp))
        }
    }
}
