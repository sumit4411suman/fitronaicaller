package com.fitron.sellagent.core.service

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.app.role.RoleManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.fitron.sellagent.R
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Keeps the process alive while the phone is connected to the backend and a call is active or expected.
 *
 * Foreground-service types are taken from the manifest entry of this service (ServiceInfo.foregroundServiceType)
 * and filtered by what Android 14+ actually permits at runtime:
 *  - phoneCall  : only when this app holds ROLE_DIALER (otherwise startForeground throws SecurityException on API 34+)
 *  - microphone : only when RECORD_AUDIO is granted (and the app is in the foreground when the service starts)
 *  - dataSync   : fallback that needs no special eligibility (Android 15 limits it to 6 h per 24 h)
 * The outcome (types used, or the failure) is published so the UI and the capability report can show the truth.
 */
class ConnectionForegroundService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopForegroundCompat()
            stopSelf()
            return START_NOT_STICKY
        }
        val reason = intent?.getStringExtra(EXTRA_REASON) ?: getString(R.string.fgs_default_reason)
        ensureChannel()
        val notification = buildNotification(reason)
        val manifestTypes = manifestForegroundTypes()
        var types = 0
        if (manifestTypes and ServiceInfo.FOREGROUND_SERVICE_TYPE_PHONE_CALL != 0 &&
            (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE || isDefaultDialer())
        ) {
            types = types or ServiceInfo.FOREGROUND_SERVICE_TYPE_PHONE_CALL
        }
        if (manifestTypes and ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE != 0 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
        ) {
            types = types or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
        }
        if (types == 0 && manifestTypes and ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC != 0) {
            types = ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
        }
        val first = runCatching { ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, types) }
        if (first.isSuccess) {
            publish(true, types, "startForeground ok with types ${describeTypes(types)}")
            return START_STICKY
        }
        val fallback = ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
        val second = if (types != fallback && manifestTypes and fallback != 0) {
            runCatching { ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, fallback) }
        } else {
            first
        }
        if (second.isSuccess) {
            publish(true, fallback, "types ${describeTypes(types)} refused (${first.exceptionOrNull()?.javaClass?.simpleName}); running as dataSync")
            return START_STICKY
        }
        publish(false, 0, "startForeground failed: ${second.exceptionOrNull()?.javaClass?.simpleName}: ${second.exceptionOrNull()?.message}")
        stopSelf()
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        publish(false, 0, "service stopped")
        super.onDestroy()
    }

    private fun stopForegroundCompat() {
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
    }

    private fun manifestForegroundTypes(): Int = runCatching {
        val cn = ComponentName(this, ConnectionForegroundService::class.java)
        val info = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            packageManager.getServiceInfo(cn, PackageManager.ComponentInfoFlags.of(0))
        } else {
            legacyServiceInfo(cn)
        }
        info.foregroundServiceType
    }.getOrDefault(0)

    @Suppress("DEPRECATION")
    private fun legacyServiceInfo(cn: ComponentName): ServiceInfo = packageManager.getServiceInfo(cn, 0)

    private fun isDefaultDialer(): Boolean {
        val rm = getSystemService(Context.ROLE_SERVICE) as? RoleManager ?: return false
        return runCatching { rm.isRoleHeld(RoleManager.ROLE_DIALER) }.getOrDefault(false)
    }

    private fun ensureChannel() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (nm.getNotificationChannel(CHANNEL_ID) == null) {
            val channel = NotificationChannel(CHANNEL_ID, getString(R.string.fgs_channel_name), NotificationManager.IMPORTANCE_LOW)
            channel.description = getString(R.string.fgs_channel_description)
            channel.setShowBadge(false)
            nm.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(reason: String): Notification {
        val launch = packageManager.getLaunchIntentForPackage(packageName)
        val pending = launch?.let {
            PendingIntent.getActivity(this, 0, it, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        }
        val builder = Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_sellagent)
            .setColor(ContextCompat.getColor(this, R.color.brand_gold))
            .setContentTitle(getString(R.string.fgs_title))
            .setContentText(reason)
            .setOngoing(true)
            .setCategory(Notification.CATEGORY_SERVICE)
        if (pending != null) builder.setContentIntent(pending)
        return builder.build()
    }

    private fun publish(running: Boolean, types: Int, detail: String) {
        _running.value = running
        _typesInUse.value = types
        _lastDetail.value = detail
    }

    companion object {
        const val CHANNEL_ID = "sellagent_connection"
        const val NOTIFICATION_ID = 1001
        private const val ACTION_STOP = "com.fitron.sellagent.action.STOP_FGS"
        private const val EXTRA_REASON = "reason"

        private val _running = MutableStateFlow(false)
        /** True only after startForeground succeeded; this is what feeds supports_foreground_service. */
        val running: StateFlow<Boolean> = _running

        private val _typesInUse = MutableStateFlow(0)
        val typesInUse: StateFlow<Int> = _typesInUse

        private val _lastDetail = MutableStateFlow("")
        val lastDetail: StateFlow<String> = _lastDetail

        fun start(context: Context, reason: String) {
            val intent = Intent(context, ConnectionForegroundService::class.java).putExtra(EXTRA_REASON, reason)
            runCatching { ContextCompat.startForegroundService(context, intent) }
                .onFailure { _lastDetail.value = "startForegroundService failed: ${it.javaClass.simpleName}" }
        }

        fun stop(context: Context) {
            val intent = Intent(context, ConnectionForegroundService::class.java).setAction(ACTION_STOP)
            runCatching { context.startService(intent) }.onFailure { runCatching { context.stopService(intent) } }
        }

        fun describeTypes(types: Int): String {
            val names = mutableListOf<String>()
            if (types and ServiceInfo.FOREGROUND_SERVICE_TYPE_PHONE_CALL != 0) names.add("phoneCall")
            if (types and ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE != 0) names.add("microphone")
            if (types and ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC != 0) names.add("dataSync")
            return if (names.isEmpty()) "none" else names.joinToString("|")
        }
    }
}
