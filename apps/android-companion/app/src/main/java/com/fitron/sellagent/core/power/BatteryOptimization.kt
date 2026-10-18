package com.fitron.sellagent.core.power

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings
import com.fitron.sellagent.core.log.AppLog

/**
 * Battery-optimization (Doze / App Standby) exemption. The state shown is always the real value of
 * PowerManager.isIgnoringBatteryOptimizations(packageName). The direct request dialog uses
 * REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, which Google Play restricts; these apps are sideloaded for a single
 * operator device, so the request is legitimate here. Every launch has a settings-list fallback.
 */
object BatteryOptimization {
    fun isIgnoring(context: Context): Boolean? {
        val pm = context.getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return null
        return runCatching { pm.isIgnoringBatteryOptimizations(context.packageName) }.getOrNull()
    }

    /** Short machine-readable note for DeviceCapabilities.notes. */
    fun note(context: Context): String = "battery_optimization_ignored=" + (isIgnoring(context)?.toString() ?: "unknown")

    /** Opens the system "allow this app to ignore battery optimizations" dialog, falling back to the settings list. */
    @SuppressLint("BatteryLife")
    fun requestExemption(context: Context): String {
        val direct = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + context.packageName))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val ok = runCatching { context.startActivity(direct) }.isSuccess
        if (ok) {
            AppLog.i(TAG, "opened ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS")
            return "ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS"
        }
        return openSettingsList(context)
    }

    fun openSettingsList(context: Context): String {
        val list = Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val ok = runCatching { context.startActivity(list) }.isSuccess
        AppLog.i(TAG, "opened ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS ok=$ok")
        return if (ok) "ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS" else "no battery settings activity found"
    }

    /** Samsung "Never sleeping apps" lives under the app's battery page; app details is the documented entry point. */
    fun openAppDetails(context: Context): Boolean {
        val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        return runCatching { context.startActivity(intent) }.isSuccess
    }

    private const val TAG = "battery"
}
