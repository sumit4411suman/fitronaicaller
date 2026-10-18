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
import androidx.compose.material3.OutlinedTextField
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
import com.fitron.sellagent.core.AppInfo
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.net.ConnectionState
import com.fitron.sellagent.core.telecom.SellAgentInCallService
import com.fitron.sellagent.protocol.NetworkKind
import com.fitron.sellagent.protocol.PROTOCOL_VERSION

@Composable
fun connectionLabel(state: ConnectionState): Pair<String, Tone> = when (state) {
    ConnectionState.Stopped -> stringResource(R.string.conn_stopped) to Tone.Neutral
    ConnectionState.Unpaired -> stringResource(R.string.conn_unpaired) to Tone.Warn
    ConnectionState.Connecting -> stringResource(R.string.conn_connecting) to Tone.Info
    is ConnectionState.Connected -> stringResource(R.string.conn_connected, state.backendName) to Tone.Good
    is ConnectionState.Backoff -> stringResource(R.string.conn_backoff, state.retryInSeconds, state.reason) to Tone.Bad
}

/** Short chip label: "Connected to PC" / "Not connected". */
@Composable
fun connectionChip(state: ConnectionState): Pair<String, Tone> =
    if (state is ConnectionState.Connected) stringResource(R.string.chip_connected) to Tone.Good else stringResource(R.string.chip_not_connected) to Tone.Bad

@Composable
fun wifiCallingLabel(observed: Boolean?): Pair<String, Tone> = when (observed) {
    true -> stringResource(R.string.wifi_calling_active) to Tone.Good
    false -> stringResource(R.string.wifi_calling_not_on_this_call) to Tone.Neutral
    null -> stringResource(R.string.unknown_no_public_api) to Tone.Neutral
}

/** "Device Connection" screen: connection banner, device facts, Disconnect, and the pairing form when unpaired. */
@Composable
fun PairingScreen(appLabel: String, vm: PairingViewModel = viewModel()) {
    val context = LocalContext.current
    val core = context.core()
    val pairing by core.store.pairing.collectAsStateWithLifecycle()
    val connection by core.socket.state.collectAsStateWithLifecycle()
    val log by core.socket.log.collectAsStateWithLifecycle()
    val wifiCall by SellAgentInCallService.wifiCallObserved.collectAsStateWithLifecycle()
    val host by vm.host.collectAsStateWithLifecycle()
    val port by vm.port.collectAsStateWithLifecycle()
    val code by vm.code.collectAsStateWithLifecycle()
    val fp by vm.fingerprint.collectAsStateWithLifecycle()
    val status by vm.status.collectAsStateWithLifecycle()

    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.pairing_title), stringResource(R.string.pairing_subtitle, PROTOCOL_VERSION))
        val (chipText, chipTone) = connectionChip(connection)
        BannerCard(chipText + (pairing?.let { " · ${it.backendName}" } ?: ""), chipTone)

        SectionCard(stringResource(R.string.pairing_connection)) {
            val (label, tone) = connectionLabel(connection)
            KeyValueRow(stringResource(R.string.pairing_state), label, tone)
            KeyValueRow(stringResource(R.string.status_device), AppInfo.deviceModel(), Tone.Neutral)
            KeyValueRow(stringResource(R.string.settings_android), AppInfo.androidVersion(), Tone.Neutral)
            val net = AppInfo.networkKind(context)
            KeyValueRow(stringResource(R.string.status_network), net, if (net == NetworkKind.WIFI) Tone.Good else Tone.Warn)
            KeyValueRow(stringResource(R.string.status_battery), AppInfo.batteryPercent(context)?.let { "$it %" } ?: "-", Tone.Neutral)
            val (wifiText, wifiTone) = wifiCallingLabel(wifiCall)
            KeyValueRow(stringResource(R.string.call_wifi_calling), wifiText, wifiTone)
            KeyValueRow(stringResource(R.string.settings_app_version), AppInfo.appVersion(context), Tone.Neutral)
            val p = pairing
            if (p != null) {
                KeyValueRow(stringResource(R.string.pairing_device_id), p.deviceId.take(12), Tone.Neutral)
                KeyValueRow(stringResource(R.string.pairing_endpoint), "${p.host}:${p.port}", Tone.Neutral)
                KeyValueRow(stringResource(R.string.pairing_pinned_fp), p.tlsFingerprint.take(23) + "…", Tone.Good)
                MutedText(stringResource(R.string.pairing_token_hidden))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlineButton(stringResource(R.string.pairing_reconnect)) { core.socket.reconnectNow() }
                    DangerOutlineButton(stringResource(R.string.pairing_disconnect)) { vm.forget() }
                }
            }
        }

        if (pairing == null) {
            SectionCard(stringResource(R.string.pairing_form_title)) {
                MutedText(stringResource(R.string.pairing_form_help))
                val fieldColors = brandFieldColors()
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

        SectionCard(stringResource(R.string.pairing_security_title)) { MutedText(stringResource(R.string.pairing_security_text)) }
        SectionCard(stringResource(R.string.transport_log)) { LogList(log) }
        Text("", modifier = Modifier.padding(8.dp))
    }
}
