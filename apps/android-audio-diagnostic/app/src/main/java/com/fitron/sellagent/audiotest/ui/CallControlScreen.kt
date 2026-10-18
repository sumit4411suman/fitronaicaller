package com.fitron.sellagent.audiotest.ui

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.telecom.TelecomManager
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.R
import com.fitron.sellagent.audiotest.DiagnosticApp
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.service.ConnectionForegroundService
import com.fitron.sellagent.core.telecom.AudioRouting
import com.fitron.sellagent.core.telecom.CallMonitor
import com.fitron.sellagent.core.telecom.SellAgentInCallService
import com.fitron.sellagent.core.ui.AppHeader
import com.fitron.sellagent.core.ui.DangerButton
import com.fitron.sellagent.core.ui.GoldButton
import com.fitron.sellagent.core.ui.KeyValueRow
import com.fitron.sellagent.core.ui.OutlineButton
import com.fitron.sellagent.core.ui.SectionCard
import com.fitron.sellagent.core.ui.Tone
import com.fitron.sellagent.protocol.AudioRoute

private val E164 = Regex("^\\+[1-9][0-9]{6,14}$")

/** Places a call through TelecomManager.placeCall. Returns a human-readable outcome; never throws. */
fun placeTestCall(context: Context, number: String, onNote: (String) -> Unit): String {
    if (!E164.matches(number)) return context.getString(R.string.call_number_invalid)
    if (ContextCompat.checkSelfPermission(context, Manifest.permission.CALL_PHONE) != PackageManager.PERMISSION_GRANTED) {
        return context.getString(R.string.call_dial_denied)
    }
    val tm = context.getSystemService(Context.TELECOM_SERVICE) as? TelecomManager ?: return "TelecomManager unavailable"
    return try {
        tm.placeCall(Uri.fromParts("tel", number, null), Bundle())
        onNote("placeCall(${number.take(4)}…) issued")
        context.getString(R.string.call_dial_result_ok)
    } catch (e: SecurityException) {
        onNote("placeCall SecurityException: ${e.message}")
        "SecurityException: ${e.message}"
    } catch (e: Exception) {
        onNote("placeCall ${e.javaClass.simpleName}: ${e.message}")
        "${e.javaClass.simpleName}: ${e.message}"
    }
}

@Composable
fun CallControlScreen() {
    val context = LocalContext.current
    val core = context.core()
    val session = (context.applicationContext as DiagnosticApp).session
    val coarse by core.callMonitor.state.collectAsStateWithLifecycle()
    val registered by core.callMonitor.registered.collectAsStateWithLifecycle()
    val bound by SellAgentInCallService.bound.collectAsStateWithLifecycle()
    val detailed by SellAgentInCallService.lastEvent.collectAsStateWithLifecycle()
    val icsRoute by SellAgentInCallService.audioRoute.collectAsStateWithLifecycle()
    val estop by core.socket.emergencyStopActive.collectAsStateWithLifecycle()
    var number by rememberSaveable { mutableStateOf("") }
    var lastAction by rememberSaveable { mutableStateOf("") }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.call_title), stringResource(R.string.call_subtitle))
        SectionCard(stringResource(R.string.call_dial)) {
            OutlinedTextField(
                value = number,
                onValueChange = { number = it.filter { c -> c.isDigit() || c == '+' } },
                label = { Text(stringResource(R.string.call_number)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                modifier = Modifier.fillMaxWidth(),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = BrandColors.Gold, unfocusedBorderColor = BrandColors.SurfaceBorder,
                    focusedLabelColor = BrandColors.Gold, unfocusedLabelColor = BrandColors.TextSecondary,
                    cursorColor = BrandColors.Gold, focusedTextColor = BrandColors.TextPrimary, unfocusedTextColor = BrandColors.TextPrimary,
                ),
            )
            if (estop) Text(stringResource(R.string.call_emergency_blocked), style = MaterialTheme.typography.bodySmall, color = BrandColors.Danger)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GoldButton(stringResource(R.string.call_dial), enabled = !estop) {
                    ConnectionForegroundService.start(context, context.getString(R.string.call_title))
                    lastAction = placeTestCall(context, number) { session.note(it) }
                }
                DangerButton(stringResource(R.string.call_end), enabled = bound) {
                    val ok = SellAgentInCallService.endActiveCall()
                    lastAction = "InCallService disconnect: $ok"
                    session.note("end call via InCallService: $ok")
                }
            }
            if (!bound) Text(stringResource(R.string.call_end_hint), style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary)
            if (lastAction.isNotBlank()) KeyValueRow(stringResource(R.string.call_last_action), lastAction, Tone.Info)
        }

        SectionCard(stringResource(R.string.call_coarse)) {
            KeyValueRow("TelephonyCallback registered", if (registered) stringResource(R.string.yes) else stringResource(R.string.no), if (registered) Tone.Good else Tone.Warn)
            KeyValueRow(CallMonitor.describe(coarse.telephonyState), coarse.protocolState, if (coarse.telephonyState == 0) Tone.Neutral else Tone.Good)
        }

        SectionCard(stringResource(R.string.call_detailed)) {
            if (!bound) {
                Text(stringResource(R.string.call_not_bound), style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)
            } else {
                val d = detailed
                KeyValueRow("Call state", d?.let { "${SellAgentInCallService.describeState(it.telecomState)} -> ${it.protocolState}" } ?: "-", Tone.Good)
                KeyValueRow("Disconnect cause", d?.disconnectCause ?: "-", Tone.Neutral)
                KeyValueRow(stringResource(R.string.call_route), icsRoute, Tone.Neutral)
            }
        }

        SectionCard(stringResource(R.string.call_routes_title)) {
            var routeNote by rememberSaveable { mutableStateOf("") }
            KeyValueRow(stringResource(R.string.call_route), AudioRouting.currentRoute(context), Tone.Neutral)
            KeyValueRow(stringResource(R.string.call_wifi_calling), stringResource(R.string.unknown_no_public_api), Tone.Neutral)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf(AudioRoute.EARPIECE, AudioRoute.SPEAKER).forEach { r ->
                    OutlineButton(r, modifier = Modifier.weight(1f)) {
                        val res = AudioRouting.setRoute(context, r)
                        routeNote = "${res.apiUsed}: ok=${res.ok} ${res.detail}"
                        session.note("route $r via ${res.apiUsed}: ok=${res.ok}")
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf(AudioRoute.BLUETOOTH, AudioRoute.WIRED_HEADSET).forEach { r ->
                    OutlineButton(r, modifier = Modifier.weight(1f)) {
                        val res = AudioRouting.setRoute(context, r)
                        routeNote = "${res.apiUsed}: ok=${res.ok} ${res.detail}"
                        session.note("route $r via ${res.apiUsed}: ok=${res.ok}")
                    }
                }
            }
            if (routeNote.isNotBlank()) Text(routeNote, style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary)
        }

        DangerButton(stringResource(R.string.runner_emergency_stop), modifier = Modifier.fillMaxWidth().padding(16.dp).height(56.dp)) {
            session.emergencyStop("operator pressed emergency stop on call screen")
        }
    }
}
