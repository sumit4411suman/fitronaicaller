package com.fitron.sellagent.core.ui

import android.Manifest
import android.app.role.RoleManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.R
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.service.ConnectionForegroundService
import com.fitron.sellagent.core.telecom.SellAgentInCallService

/** Permissions & Capabilities screen shared by both apps. Every row reflects a value read from the platform right now. */
@Composable
fun PermissionsScreen() {
    val context = LocalContext.current
    val core = context.core()
    var tick by remember { mutableIntStateOf(0) }
    val refresh = { tick++ }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { refresh() }

    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        core.callMonitor.start()
        refresh()
    }
    val roleLauncher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { refresh() }

    val monitorRegistered by core.callMonitor.registered.collectAsStateWithLifecycle()
    val inCallBound by SellAgentInCallService.bound.collectAsStateWithLifecycle()
    val fgsRunning by ConnectionForegroundService.running.collectAsStateWithLifecycle()
    val fgsDetail by ConnectionForegroundService.lastDetail.collectAsStateWithLifecycle()
    val fgsTypes by ConnectionForegroundService.typesInUse.collectAsStateWithLifecycle()
    val connection by core.socket.state.collectAsStateWithLifecycle()

    // `tick` is read so that the rows recompute after permission dialogs / settings return.
    val permissions = remember(tick) { core.probe.runtimePermissions().map { it to core.probe.granted(it) } }
    val isDefaultDialer = remember(tick, inCallBound) { core.probe.isDefaultDialer() }
    val caps = remember(tick, monitorRegistered, inCallBound, fgsRunning) { core.capabilities() }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.perm_title), stringResource(R.string.perm_subtitle))

        SectionCard(stringResource(R.string.perm_runtime)) {
            permissions.forEach { (perm, granted) ->
                KeyValueRow(
                    permissionLabel(perm),
                    if (granted) stringResource(R.string.granted) else stringResource(R.string.not_granted),
                    if (granted) Tone.Good else Tone.Bad,
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GoldButton(stringResource(R.string.perm_request_all)) {
                    permissionLauncher.launch(core.probe.runtimePermissions().toTypedArray())
                }
                OutlineButton(stringResource(R.string.perm_open_settings)) {
                    val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
                    runCatching { context.startActivity(intent) }
                }
            }
        }

        SectionCard(stringResource(R.string.perm_dialer_title)) {
            Text(stringResource(R.string.perm_dialer_why), style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)
            KeyValueRow(stringResource(R.string.perm_dialer_role), yesNo(isDefaultDialer), if (isDefaultDialer) Tone.Good else Tone.Warn)
            KeyValueRow(stringResource(R.string.perm_incall_bound), yesNo(inCallBound), if (inCallBound) Tone.Good else Tone.Neutral)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GoldButton(stringResource(R.string.perm_request_dialer), enabled = !isDefaultDialer) {
                    val rm = context.getSystemService(Context.ROLE_SERVICE) as? RoleManager
                    val intent = rm?.takeIf { it.isRoleAvailable(RoleManager.ROLE_DIALER) }?.createRequestRoleIntent(RoleManager.ROLE_DIALER)
                    if (intent != null) roleLauncher.launch(intent)
                }
                OutlineButton(stringResource(R.string.perm_default_apps)) {
                    runCatching { context.startActivity(Intent(Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS)) }
                }
            }
        }

        SectionCard(stringResource(R.string.perm_fgs_title)) {
            KeyValueRow(stringResource(R.string.perm_fgs_running), yesNo(fgsRunning), if (fgsRunning) Tone.Good else Tone.Neutral)
            KeyValueRow(stringResource(R.string.perm_fgs_types), ConnectionForegroundService.describeTypes(fgsTypes), Tone.Neutral)
            if (fgsDetail.isNotBlank()) Text(fgsDetail, style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GoldButton(stringResource(R.string.perm_fgs_start)) {
                    ConnectionForegroundService.start(context, context.getString(R.string.fgs_reason_verify))
                }
                OutlineButton(stringResource(R.string.perm_fgs_stop)) { ConnectionForegroundService.stop(context) }
            }
        }

        SectionCard(stringResource(R.string.perm_caps_title)) {
            Text(stringResource(R.string.perm_caps_help), style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)
            CapRow(stringResource(R.string.cap_can_place_calls), caps.canPlaceCalls, "CALL_PHONE")
            CapRow(stringResource(R.string.cap_reports_call_state), caps.reportsCallState, "READ_PHONE_STATE + TelephonyCallback")
            CapRow(stringResource(R.string.cap_is_default_dialer), caps.isDefaultDialer, "RoleManager.ROLE_DIALER")
            CapRow(stringResource(R.string.cap_can_control_audio_route), caps.canControlAudioRoute, "InCallService bound")
            CapRow(stringResource(R.string.cap_can_end_calls), caps.canEndCalls, "InCallService bound")
            CapRow(stringResource(R.string.cap_supports_fgs), caps.supportsForegroundService, "startForeground ok")
            CapRow(stringResource(R.string.cap_remote_capture), caps.remoteAudioCaptureVerified, stringResource(R.string.cap_backend_only))
            CapRow(stringResource(R.string.cap_injection), caps.audioInjectionVerified, stringResource(R.string.cap_backend_only))
            KeyValueRow(
                stringResource(R.string.cap_wifi_calling),
                when (caps.wifiCallingActive) { true -> stringResource(R.string.yes); false -> stringResource(R.string.no); null -> stringResource(R.string.unknown_no_public_api) },
                Tone.Neutral,
            )
            KeyValueRow("android_sdk_int", caps.androidSdkInt?.toString() ?: "-", Tone.Neutral)
            KeyValueRow("device_model", caps.deviceModel ?: "-", Tone.Neutral)
            KeyValueRow("app_version", caps.appVersion ?: "-", Tone.Neutral)
            val connected = connection is com.fitron.sellagent.core.net.ConnectionState.Connected
            GoldButton(stringResource(R.string.perm_send_caps), enabled = connected) { core.sendCapabilities() }
            if (!connected) Text(stringResource(R.string.perm_send_caps_offline), style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary)
        }

        SectionCard(stringResource(R.string.perm_limits_title)) {
            Text(stringResource(R.string.perm_limits_text), style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)
        }
        Text("", modifier = Modifier.padding(8.dp))
    }
}

@Composable
private fun CapRow(label: String, value: Boolean, source: String) {
    Column {
        KeyValueRow(label, yesNo(value), if (value) Tone.Good else Tone.Neutral)
        Text(source, style = MaterialTheme.typography.labelSmall, color = BrandColors.TextDisabled, modifier = Modifier.padding(start = 18.dp))
    }
}

@Composable
fun yesNo(v: Boolean): String = if (v) stringResource(R.string.yes) else stringResource(R.string.no)

@Composable
fun permissionLabel(permission: String): String = when (permission) {
    Manifest.permission.CALL_PHONE -> "CALL_PHONE"
    Manifest.permission.READ_PHONE_STATE -> "READ_PHONE_STATE"
    Manifest.permission.RECORD_AUDIO -> "RECORD_AUDIO"
    Manifest.permission.POST_NOTIFICATIONS -> "POST_NOTIFICATIONS"
    Manifest.permission.BLUETOOTH_CONNECT -> "BLUETOOTH_CONNECT"
    else -> permission.substringAfterLast('.')
}
