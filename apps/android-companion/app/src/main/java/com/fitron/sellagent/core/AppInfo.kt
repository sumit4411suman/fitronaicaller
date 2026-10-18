package com.fitron.sellagent.core

import android.content.Context
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Build
import android.provider.Settings
import com.fitron.sellagent.protocol.NetworkKind

/** Read-only facts about this device/app, all from public APIs. */
object AppInfo {
    fun deviceModel(): String = "${Build.MANUFACTURER} ${Build.MODEL}".trim().take(80)

    fun androidVersion(): String = "Android ${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})".take(40)

    fun deviceName(context: Context): String {
        val name = runCatching { Settings.Global.getString(context.contentResolver, Settings.Global.DEVICE_NAME) }.getOrNull()
        return (name?.takeIf { it.isNotBlank() } ?: Build.MODEL).take(80)
    }

    fun appVersion(context: Context): String {
        val info = runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                context.packageManager.getPackageInfo(context.packageName, PackageManager.PackageInfoFlags.of(0))
            } else {
                legacyPackageInfo(context)
            }
        }.getOrNull()
        return (info?.versionName ?: "0.0.0").take(40)
    }

    @Suppress("DEPRECATION")
    private fun legacyPackageInfo(context: Context): PackageInfo =
        context.packageManager.getPackageInfo(context.packageName, 0)

    fun batteryPercent(context: Context): Int? {
        val bm = context.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager ?: return null
        val v = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        return if (v in 0..100) v else null
    }

    fun networkKind(context: Context): String {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return NetworkKind.UNKNOWN
        val network = cm.activeNetwork ?: return NetworkKind.NONE
        val caps = cm.getNetworkCapabilities(network) ?: return NetworkKind.UNKNOWN
        return when {
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> NetworkKind.WIFI
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> NetworkKind.CELLULAR
            else -> NetworkKind.UNKNOWN
        }
    }
}
