package com.fitron.sellagent.core.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.fitron.sellagent.R
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.net.ConnectionState
import com.fitron.sellagent.protocol.PROTOCOL_VERSION

@Composable
fun connectionLabel(state: ConnectionState): Pair<String, Tone> = when (state) {
    ConnectionState.Stopped -> stringResource(R.string.conn_stopped) to Tone.Neutral
    ConnectionState.Unpaired -> stringResource(R.string.conn_unpaired) to Tone.Warn
    ConnectionState.Connecting -> stringResource(R.string.conn_connecting) to Tone.Info
    is ConnectionState.Connected -> stringResource(R.string.conn_connected, state.backendName) to Tone.Good
    is ConnectionState.Backoff -> stringResource(R.string.conn_backoff, state.retryInSeconds, state.reason) to Tone.Bad
}

@Composable
fun PairingScreen(appLabel: String, vm: PairingViewModel = viewModel()) {
    val core = LocalContext.current.core()
    val pairing by core.store.pairing.collectAsStateWithLifecycle()
    val connection by core.socket.state.collectAsStateWithLifecycle()
    val log by core.socket.log.collectAsStateWithLifecycle()
    val host by vm.host.collectAsStateWithLifecycle()
    val port by vm.port.collectAsStateWithLifecycle()
    val code by vm.code.collectAsStateWithLifecycle()
    val fp by vm.fingerprint.collectAsStateWithLifecycle()
    val status by vm.status.collectAsStateWithLifecycle()

    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.pairing_title), stringResource(R.string.pairing_subtitle, PROTOCOL_VERSION))

        SectionCard(stringResource(R.string.pairing_connection)) {
            val (label, tone) = connectionLabel(connection)
            KeyValueRow(stringResource(R.string.pairing_state), label, tone)
            if (pairing != null) {
                KeyValueRow(stringResource(R.string.pairing_backend), pairing!!.backendName, Tone.Good)
                KeyValueRow(stringResource(R.string.pairing_device_id), pairing!!.deviceId.take(12), Tone.Neutral)
                KeyValueRow(stringResource(R.string.pairing_endpoint), "${pairing!!.host}:${pairing!!.port}", Tone.Neutral)
                KeyValueRow(stringResource(R.string.pairing_pinned_fp), pairing!!.tlsFingerprint.take(23) + "…", Tone.Good)
                Text(stringResource(R.string.pairing_token_hidden), style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlineButton(stringResource(R.string.pairing_reconnect)) { core.socket.reconnectNow() }
                    DangerButton(stringResource(R.string.pairing_forget)) { vm.forget() }
                }
            }
        }

        if (pairing == null) {
            SectionCard(stringResource(R.string.pairing_form_title)) {
                Text(stringResource(R.string.pairing_form_help), style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)
                val fieldColors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = BrandColors.Gold,
                    unfocusedBorderColor = BrandColors.SurfaceBorder,
                    focusedLabelColor = BrandColors.Gold,
                    unfocusedLabelColor = BrandColors.TextSecondary,
                    cursorColor = BrandColors.Gold,
                    focusedTextColor = BrandColors.TextPrimary,
                    unfocusedTextColor = BrandColors.TextPrimary,
                )
                OutlinedTextField(
                    value = host, onValueChange = vm::setHost, singleLine = true, colors = fieldColors,
                    label = { Text(stringResource(R.string.pairing_host)) }, modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                )
                OutlinedTextField(
                    value = port, onValueChange = vm::setPort, singleLine = true, colors = fieldColors,
                    label = { Text(stringResource(R.string.pairing_port)) }, modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                )
                OutlinedTextField(
                    value = code, onValueChange = vm::setCode, singleLine = true, colors = fieldColors,
                    label = { Text(stringResource(R.string.pairing_code)) }, modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii),
                )
                OutlinedTextField(
                    value = fp, onValueChange = vm::setFingerprint, singleLine = false, minLines = 2, colors = fieldColors,
                    label = { Text(stringResource(R.string.pairing_fingerprint)) }, modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii),
                )
                val busy = status is PairingUiStatus.Checking || status is PairingUiStatus.WaitingApproval
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    GoldButton(stringResource(R.string.pairing_pair), enabled = !busy) { vm.pair(appLabel) }
                    if (busy) OutlineButton(stringResource(R.string.cancel)) { vm.cancel() }
                }
                val (statusText, statusTone) = when (val s = status) {
                    PairingUiStatus.Idle -> stringResource(R.string.pairing_status_idle) to Tone.Neutral
                    PairingUiStatus.Checking -> stringResource(R.string.pairing_status_checking) to Tone.Info
                    is PairingUiStatus.WaitingApproval -> stringResource(R.string.pairing_status_waiting, s.polls * 2) to Tone.Info
                    PairingUiStatus.Approved -> stringResource(R.string.pairing_status_approved) to Tone.Good
                    is PairingUiStatus.Failed -> stringResource(R.string.pairing_status_failed, s.reason) to Tone.Bad
                }
                KeyValueRow(stringResource(R.string.pairing_status), statusText, statusTone)
            }
        }

        SectionCard(stringResource(R.string.pairing_security_title)) {
            Text(stringResource(R.string.pairing_security_text), style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)
        }

        SectionCard(stringResource(R.string.transport_log)) {
            LogList(log)
        }
        Text("", modifier = Modifier.padding(8.dp))
    }
}
