package com.fitron.sellagent.core.caps

import android.Manifest
import android.app.role.RoleManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import com.fitron.sellagent.core.AppInfo
import com.fitron.sellagent.core.telecom.SellAgentInCallService
import com.fitron.sellagent.protocol.DeviceCapabilities

/**
 * Derives DeviceCapabilities strictly from verified runtime facts.
 *
 *  can_place_calls            = CALL_PHONE granted
 *  reports_call_state         = READ_PHONE_STATE granted AND a TelephonyCallback is currently registered
 *  is_default_dialer          = RoleManager.isRoleHeld(ROLE_DIALER)
 *  can_control_audio_route    = our InCallService is bound (only happens when we are the default dialer)
 *  can_end_calls              = our InCallService is bound
 *  supports_foreground_service= the foreground service actually started (startForeground succeeded)
 *  remote_audio_capture_verified / audio_injection_verified = ALWAYS false from the app
 *  wifi_calling_active        = null (no public API; see wifiCallingActive())
 */
class CapabilityProbe(private val context: Context) {

    fun granted(permission: String): Boolean =
        ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED

    fun isDefaultDialer(): Boolean {
        val rm = context.getSystemService(Context.ROLE_SERVICE) as? RoleManager ?: return false
        return runCatching { rm.isRoleAvailable(RoleManager.ROLE_DIALER) && rm.isRoleHeld(RoleManager.ROLE_DIALER) }.getOrDefault(false)
    }

    /**
     * Wi-Fi calling (VoWiFi) status. `TelephonyManager#isWifiCallingAvailable` is NOT part of the public SDK
     * (hidden/system API) and `ImsMmTelManager` is system-only, so outside a call the answer is null ("unknown").
     * During a call observed by our InCallService (default dialer) the public `Call.Details.PROPERTY_WIFI` flag
     * tells whether THAT call runs over Wi-Fi; that observation is the only non-null value ever reported.
     */
    fun wifiCallingActive(): Boolean? = SellAgentInCallService.wifiCallObserved.value

    /** The list of runtime permissions the apps ask for, filtered to those that exist on this API level. */
    fun runtimePermissions(): List<String> {
        val list = mutableListOf(
            Manifest.permission.CALL_PHONE,
            Manifest.permission.READ_PHONE_STATE,
            Manifest.permission.RECORD_AUDIO,
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) list.add(Manifest.permission.BLUETOOTH_CONNECT)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) list.add(Manifest.permission.POST_NOTIFICATIONS)
        return list
    }

    fun capabilities(
        telephonyCallbackRegistered: Boolean,
        inCallServiceBound: Boolean,
        foregroundServiceVerified: Boolean,
        notes: String? = null,
    ): DeviceCapabilities = DeviceCapabilities(
        canPlaceCalls = granted(Manifest.permission.CALL_PHONE),
        reportsCallState = granted(Manifest.permission.READ_PHONE_STATE) && telephonyCallbackRegistered,
        isDefaultDialer = isDefaultDialer(),
        canControlAudioRoute = inCallServiceBound,
        canEndCalls = inCallServiceBound,
        supportsForegroundService = foregroundServiceVerified,
        remoteAudioCaptureVerified = false,
        audioInjectionVerified = false,
        wifiCallingActive = wifiCallingActive(),
        androidSdkInt = Build.VERSION.SDK_INT,
        deviceModel = AppInfo.deviceModel(),
        appVersion = AppInfo.appVersion(context),
        notes = notes,
    )
}
