package com.fitron.sellagent.core.telecom

import android.content.Context
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Build
import com.fitron.sellagent.protocol.AudioRoute

/**
 * Audio route switching. Preferred path: InCallService.setAudioRoute (only when this app is the default dialer).
 * Fallback: AudioManager.setCommunicationDevice (API 31+) or the deprecated speakerphone/SCO setters. The result
 * records which API was actually used so the diagnostic report is truthful.
 */
object AudioRouting {
    data class Result(val ok: Boolean, val apiUsed: String, val detail: String)

    fun setRoute(context: Context, protocolRoute: String): Result {
        if (SellAgentInCallService.bound.value) {
            val r = SellAgentInCallService.callAudioStateRoute(protocolRoute)
                ?: return Result(false, "InCallService.setAudioRoute", "unsupported route $protocolRoute")
            val ok = SellAgentInCallService.setRoute(r)
            return Result(ok, "InCallService.setAudioRoute", if (ok) "requested route $protocolRoute" else "setAudioRoute threw")
        }
        val am = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
            ?: return Result(false, "AudioManager", "AudioManager unavailable")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val wanted = deviceTypesFor(protocolRoute)
            val device = am.availableCommunicationDevices.firstOrNull { it.type in wanted }
                ?: return Result(false, "AudioManager.setCommunicationDevice", "no available communication device of type $protocolRoute")
            val ok = runCatching { am.setCommunicationDevice(device) }.getOrDefault(false)
            return Result(ok, "AudioManager.setCommunicationDevice", "device=${describeDevice(device)} result=$ok")
        }
        return legacySetRoute(am, protocolRoute)
    }

    @Suppress("DEPRECATION")
    private fun legacySetRoute(am: AudioManager, protocolRoute: String): Result = when (protocolRoute) {
        AudioRoute.SPEAKER -> {
            am.isSpeakerphoneOn = true
            Result(am.isSpeakerphoneOn, "AudioManager.setSpeakerphoneOn", "speakerphone on")
        }
        AudioRoute.EARPIECE -> {
            am.isSpeakerphoneOn = false
            Result(!am.isSpeakerphoneOn, "AudioManager.setSpeakerphoneOn", "speakerphone off")
        }
        AudioRoute.BLUETOOTH -> {
            runCatching { am.startBluetoothSco(); am.isBluetoothScoOn = true }
            Result(am.isBluetoothScoOn, "AudioManager.startBluetoothSco", "sco=${am.isBluetoothScoOn}")
        }
        AudioRoute.WIRED_HEADSET -> Result(false, "AudioManager", "wired headset is selected automatically by the platform when plugged in")
        else -> Result(false, "AudioManager", "unsupported route")
    }

    @Suppress("DEPRECATION")
    private fun legacyCurrentRoute(am: AudioManager): String = when {
        am.isBluetoothScoOn -> AudioRoute.BLUETOOTH
        am.isSpeakerphoneOn -> AudioRoute.SPEAKER
        else -> AudioRoute.UNKNOWN
    }

    fun currentRoute(context: Context): String {
        if (SellAgentInCallService.bound.value && SellAgentInCallService.audioRoute.value != AudioRoute.UNKNOWN) {
            return SellAgentInCallService.audioRoute.value
        }
        val am = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return AudioRoute.UNKNOWN
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val dev = runCatching { am.communicationDevice }.getOrNull() ?: return AudioRoute.UNKNOWN
            return protocolRouteFor(dev.type)
        }
        return legacyCurrentRoute(am)
    }

    fun describeDevice(d: AudioDeviceInfo): String = "${d.productName} (type ${d.type})"

    private fun deviceTypesFor(route: String): Set<Int> = when (route) {
        AudioRoute.EARPIECE -> setOf(AudioDeviceInfo.TYPE_BUILTIN_EARPIECE)
        AudioRoute.SPEAKER -> setOf(AudioDeviceInfo.TYPE_BUILTIN_SPEAKER)
        AudioRoute.BLUETOOTH -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            setOf(AudioDeviceInfo.TYPE_BLUETOOTH_SCO, AudioDeviceInfo.TYPE_BLE_HEADSET)
        } else {
            setOf(AudioDeviceInfo.TYPE_BLUETOOTH_SCO)
        }
        AudioRoute.WIRED_HEADSET -> setOf(AudioDeviceInfo.TYPE_WIRED_HEADSET, AudioDeviceInfo.TYPE_WIRED_HEADPHONES, AudioDeviceInfo.TYPE_USB_HEADSET)
        else -> emptySet()
    }

    private fun protocolRouteFor(type: Int): String = when (type) {
        AudioDeviceInfo.TYPE_BUILTIN_EARPIECE -> AudioRoute.EARPIECE
        AudioDeviceInfo.TYPE_BUILTIN_SPEAKER -> AudioRoute.SPEAKER
        AudioDeviceInfo.TYPE_BLUETOOTH_SCO -> AudioRoute.BLUETOOTH
        AudioDeviceInfo.TYPE_WIRED_HEADSET, AudioDeviceInfo.TYPE_WIRED_HEADPHONES, AudioDeviceInfo.TYPE_USB_HEADSET -> AudioRoute.WIRED_HEADSET
        else -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && type == AudioDeviceInfo.TYPE_BLE_HEADSET) AudioRoute.BLUETOOTH else AudioRoute.UNKNOWN
    }
}
