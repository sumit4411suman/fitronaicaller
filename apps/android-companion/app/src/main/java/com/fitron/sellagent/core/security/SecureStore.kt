package com.fitron.sellagent.core.security

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/** Everything the app knows about its pairing with the backend. The token is never logged or displayed. */
data class Pairing(
    val host: String,
    val port: Int,
    val tlsFingerprint: String,
    val deviceId: String,
    val deviceToken: String,
    val backendName: String,
    val wsPath: String,
) {
    val httpsBase: String get() = "https://$host:$port"
    val wsUrl: String get() = "wss://$host:$port$wsPath"
}

/**
 * Device token + pinned TLS fingerprint live in EncryptedSharedPreferences whose master key is held in the Android
 * Keystore (androidx.security:security-crypto 1.1.0-alpha06). Nothing here is written to plain SharedPreferences.
 */
class SecureStore(context: Context) {
    private val prefs: SharedPreferences = run {
        val masterKey = MasterKey.Builder(context, MasterKey.DEFAULT_MASTER_KEY_ALIAS)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "sellagent_secure",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    private val _pairing = MutableStateFlow(readPairing())
    val pairing: StateFlow<Pairing?> = _pairing

    /** Stable random identifier for this installation; sent as `device_public_id`. Not a secret, but kept here for simplicity. */
    val devicePublicId: String
        get() {
            val existing = prefs.getString(KEY_PUBLIC_ID, null)
            if (existing != null) return existing
            val fresh = UUID.randomUUID().toString()
            prefs.edit().putString(KEY_PUBLIC_ID, fresh).apply()
            return fresh
        }

    fun savePairing(p: Pairing) {
        prefs.edit()
            .putString(KEY_HOST, p.host)
            .putInt(KEY_PORT, p.port)
            .putString(KEY_FP, p.tlsFingerprint)
            .putString(KEY_DEVICE_ID, p.deviceId)
            .putString(KEY_TOKEN, p.deviceToken)
            .putString(KEY_BACKEND, p.backendName)
            .putString(KEY_WS_PATH, p.wsPath)
            .apply()
        _pairing.value = p
    }

    fun forgetPairing() {
        prefs.edit()
            .remove(KEY_HOST).remove(KEY_PORT).remove(KEY_FP).remove(KEY_DEVICE_ID)
            .remove(KEY_TOKEN).remove(KEY_BACKEND).remove(KEY_WS_PATH)
            .apply()
        _pairing.value = null
    }

    /** Operator-entered free text describing the network for the report (SSID, SIM, VoWiFi on/off). Not secret. */
    var networkConfigNote: String
        get() = prefs.getString(KEY_NETWORK_NOTE, "") ?: ""
        set(value) = prefs.edit().putString(KEY_NETWORK_NOTE, value).apply()

    /** Local emergency-stop latch; cleared only by heartbeat_ack/reconnect_ack reporting emergency_stop_active=false. */
    var emergencyStopLatched: Boolean
        get() = prefs.getBoolean(KEY_ESTOP, false)
        set(value) = prefs.edit().putBoolean(KEY_ESTOP, value).apply()

    private fun readPairing(): Pairing? {
        val host = prefs.getString(KEY_HOST, null) ?: return null
        val token = prefs.getString(KEY_TOKEN, null) ?: return null
        val fp = prefs.getString(KEY_FP, null) ?: return null
        val deviceId = prefs.getString(KEY_DEVICE_ID, null) ?: return null
        return Pairing(
            host = host,
            port = prefs.getInt(KEY_PORT, 8766),
            tlsFingerprint = fp,
            deviceId = deviceId,
            deviceToken = token,
            backendName = prefs.getString(KEY_BACKEND, "SELL AGENT") ?: "SELL AGENT",
            wsPath = prefs.getString(KEY_WS_PATH, "/api/v1/ws/device") ?: "/api/v1/ws/device",
        )
    }

    private companion object {
        const val KEY_PUBLIC_ID = "device_public_id"
        const val KEY_HOST = "host"
        const val KEY_PORT = "port"
        const val KEY_FP = "tls_fingerprint"
        const val KEY_DEVICE_ID = "device_id"
        const val KEY_TOKEN = "device_token"
        const val KEY_BACKEND = "backend_name"
        const val KEY_WS_PATH = "ws_path"
        const val KEY_NETWORK_NOTE = "network_note"
        const val KEY_ESTOP = "emergency_stop_latched"
    }
}
