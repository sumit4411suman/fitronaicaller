package com.fitron.sellagent.core.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.viewModelScope
import com.fitron.sellagent.core.AppInfo
import com.fitron.sellagent.core.CoreHost
import com.fitron.sellagent.core.net.PairingClient
import com.fitron.sellagent.core.security.FingerprintTrust
import com.fitron.sellagent.core.security.Pairing
import com.fitron.sellagent.protocol.PairingRequest
import java.util.Locale
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

sealed class PairingUiStatus {
    data object Idle : PairingUiStatus()
    data object Checking : PairingUiStatus()
    data class WaitingApproval(val polls: Int) : PairingUiStatus()
    data object Approved : PairingUiStatus()
    data class Failed(val reason: String) : PairingUiStatus()
}

/**
 * Pairing form state lives in SavedStateHandle so rotation and process death keep what the operator typed.
 * The device token is never kept here; it goes straight into SecureStore.
 */
class PairingViewModel(app: Application, private val saved: SavedStateHandle) : AndroidViewModel(app) {
    private val core = (app as CoreHost).core

    val host: StateFlow<String> = saved.getStateFlow(KEY_HOST, "")
    val port: StateFlow<String> = saved.getStateFlow(KEY_PORT, "8766")
    val code: StateFlow<String> = saved.getStateFlow(KEY_CODE, "")
    val fingerprint: StateFlow<String> = saved.getStateFlow(KEY_FP, "")

    private val _status = MutableStateFlow<PairingUiStatus>(PairingUiStatus.Idle)
    val status: StateFlow<PairingUiStatus> = _status

    private var job: Job? = null

    fun setHost(v: String) = saved.set(KEY_HOST, v.trim())
    fun setPort(v: String) = saved.set(KEY_PORT, v.filter { it.isDigit() }.take(5))
    fun setCode(v: String) = saved.set(KEY_CODE, v.uppercase(Locale.ROOT).filter { it.isLetterOrDigit() || it == '-' }.take(12))
    fun setFingerprint(v: String) = saved.set(KEY_FP, v)

    fun pair(appLabel: String) {
        if (job?.isActive == true) return
        val h = host.value
        val p = port.value.toIntOrNull()
        val c = code.value
        val fp = FingerprintTrust.normalize(fingerprint.value)
        when {
            h.isBlank() -> { _status.value = PairingUiStatus.Failed("host_required"); return }
            p == null || p !in 1..65535 -> { _status.value = PairingUiStatus.Failed("port_invalid"); return }
            c.length < 6 -> { _status.value = PairingUiStatus.Failed("code_invalid"); return }
            fp == null -> { _status.value = PairingUiStatus.Failed("fingerprint_invalid"); return }
        }
        requireNotNull(p)
        requireNotNull(fp)
        job = viewModelScope.launch {
            _status.value = PairingUiStatus.Checking
            val client = runCatching { PairingClient(h, p, fp) }.getOrElse {
                _status.value = PairingUiStatus.Failed("client: ${it.message}")
                return@launch
            }
            // 1. TLS handshake against the pinned fingerprint + reachability.
            runCatching { client.ping() }.onFailure {
                _status.value = PairingUiStatus.Failed("tls_or_network: ${it.javaClass.simpleName}: ${it.message ?: ""}")
                return@launch
            }
            // 2. Submit the pairing request with capabilities we can verify right now.
            val app = getApplication<Application>()
            val request = PairingRequest(
                pairingCode = c,
                deviceName = "${AppInfo.deviceName(app)} ($appLabel)".take(80),
                deviceModel = AppInfo.deviceModel(),
                androidVersion = AppInfo.androidVersion(),
                appVersion = AppInfo.appVersion(app),
                devicePublicId = core.store.devicePublicId,
                capabilities = core.capabilities(),
            )
            val response = runCatching { client.pair(request) }.getOrElse {
                _status.value = PairingUiStatus.Failed("pair: ${it.javaClass.simpleName}: ${it.message ?: ""}")
                return@launch
            }
            if (response.status != "pending") {
                _status.value = PairingUiStatus.Failed("${response.status}: ${response.message ?: ""}")
                return@launch
            }
            // 3. Poll until the Windows operator approves (max 5 minutes, every 2 s).
            var polls = 0
            while (polls < 150) {
                delay(2000)
                polls++
                _status.value = PairingUiStatus.WaitingApproval(polls)
                val result = runCatching { client.pollResult(core.store.devicePublicId) }.getOrElse {
                    _status.value = PairingUiStatus.Failed("poll: ${it.javaClass.simpleName}: ${it.message ?: ""}")
                    return@launch
                }
                when (result.status) {
                    "pending", "unknown" -> Unit
                    "approved" -> {
                        val token = result.deviceToken
                        val deviceId = result.deviceId
                        if (token.isNullOrBlank() || deviceId.isNullOrBlank()) {
                            _status.value = PairingUiStatus.Failed("approved_without_token")
                            return@launch
                        }
                        core.store.savePairing(
                            Pairing(
                                host = h,
                                port = p,
                                tlsFingerprint = fp,
                                deviceId = deviceId,
                                deviceToken = token,
                                backendName = result.backendName ?: "SELL AGENT",
                                wsPath = result.wsPath ?: "/api/v1/ws/device",
                            ),
                        )
                        saved[KEY_CODE] = ""
                        _status.value = PairingUiStatus.Approved
                        core.startAll()
                        core.socket.reconnectNow()
                        return@launch
                    }
                    else -> {
                        _status.value = PairingUiStatus.Failed(result.status)
                        return@launch
                    }
                }
            }
            _status.value = PairingUiStatus.Failed("timeout")
        }
    }

    fun cancel() {
        job?.cancel()
        _status.value = PairingUiStatus.Idle
    }

    fun forget() {
        job?.cancel()
        core.store.forgetPairing()
        core.outbox.clear()
        _status.value = PairingUiStatus.Idle
    }

    private companion object {
        const val KEY_HOST = "host"
        const val KEY_PORT = "port"
        const val KEY_CODE = "code"
        const val KEY_FP = "fp"
    }
}
