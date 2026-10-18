# SELL AGENT - Android Cellular Audio Feasibility (documented-API analysis)

Research date: 2026-10-18. Target device: Samsung Galaxy S25 (One UI 7/8, Android 15/16), Jio SIM with VoLTE and Wi-Fi Calling. No physical device was available in this session; every row of the test report below is NOT TESTED.

Sources were read from the AOSP mirror on GitHub (`aosp-mirror/platform_frameworks_base`, branch `main`) and from developer.android.com guide pages. The reference pages under developer.android.com/reference returned only navigation text to the fetch tool, so Javadoc quotes come from the source files. `android.googlesource.com` was not reachable.

## 1. What a third-party app can observe and control

| Capability | API | Permission / role | Third-party app gets it? | Source |
|---|---|---|---|---|
| Coarse call state (IDLE / RINGING / OFFHOOK) | `TelephonyCallback.CallStateListener.onCallStateChanged` | `READ_PHONE_STATE` (dangerous, runtime) | Yes. The far-end number is deliberately not delivered: "We purposely do not include the phone number as that information is not required for call state listeners going forward." | core/java/android/telephony/TelephonyCallback.java, retrieved 2026-10-18 |
| Synchronous call state | `TelephonyManager.getCallStateForSubscription()` (`getCallState()` is deprecated) | `READ_PHONE_STATE` | Yes | telephony/java/android/telephony/TelephonyManager.java |
| Number of the other party | `PHONE_STATE` broadcast / legacy `PhoneStateListener` | `READ_CALL_LOG` (+ `READ_PHONE_STATE` for the broadcast) | Only with the call-log permission; Play policy restricts that group | developer.android.com/about/versions/pie/android-9.0-changes-all |
| Detailed `Call` objects, states (`STATE_DIALING`, `STATE_ACTIVE`, `STATE_HOLDING`, `STATE_DISCONNECTED`), `disconnect()`, `answer()`, DTMF, hold | `InCallService` bound by Telecom when the app holds `RoleManager.ROLE_DIALER` | Service declared with `android.permission.BIND_INCALL_SERVICE` (protection level `signature|privileged` in core/res/AndroidManifest.xml, so only the system binds it); `<meta-data android:name="android.telecom.IN_CALL_SERVICE_UI">`; user must accept the role request | Yes, if the user makes the app the default dialer. The app "must not have any calling capability, and must consist solely of the user interface for calling" and must handle all calls. | telecomm/java/android/telecom/InCallService.java; developer.android.com/develop/connectivity/telecom/dialer-app |
| Audio route (earpiece / speaker / wired / Bluetooth) | `InCallService.setAudioRoute(int)` (deprecated) -> `requestCallEndpointChange(CallEndpoint, ...)`; `onCallEndpointChanged`, `onAvailableCallEndpointsChanged`, `setMuted` | Default dialer only | Yes (route and mute only) | InCallService.java |
| Placing a call | `TelecomManager.placeCall(Uri, Bundle)` or `ACTION_CALL` | `CALL_PHONE` (dangerous) | Yes | core/res/AndroidManifest.xml |
| Wi-Fi call indication | `Call.Details.PROPERTY_WIFI` ("Connection is using WIFI"), public, no `@hide` | Default dialer | Yes | telecomm/java/android/telecom/Call.java |
| Wi-Fi calling availability on the SIM | `TelephonyManager.isWifiCallingAvailable()` | none; annotated `@hide`, `@Deprecated`, `@UnsupportedAppUsage` | No public API. `isImsRegistered()` and `isVolteAvailable()` are also `@hide`; their documented replacements (`ImsMmTelManager.getRegistrationState`, `isAvailable`) sit behind `READ_PRECISE_PHONE_STATE`, which is `signature|privileged`. | TelephonyManager.java; core/res/AndroidManifest.xml |

What a default dialer does NOT get: the call audio samples in either direction, the ability to inject audio into the uplink, the far-end number without call-log permission, IMS registration detail, or any guarantee that the OEM dialer's extra features (Samsung call recording, Call Assist) are exposed to it.

## 2. Capturing the far end during a cellular call

Quotes from `media/java/android/media/MediaRecorder.java` (AudioSource), retrieved 2026-10-18:

- `VOICE_UPLINK`: "Voice call uplink (Tx) audio source. Capturing from VOICE_UPLINK source requires the android.Manifest.permission#CAPTURE_AUDIO_OUTPUT permission. This permission is reserved for use by system components and is not available to third-party applications."
- `VOICE_DOWNLINK`: "Voice call downlink (Rx) audio source." Same permission sentence.
- `VOICE_CALL`: "Voice call uplink + downlink audio source." Same permission sentence.
- `VOICE_COMMUNICATION`: "Microphone audio source tuned for voice communications such as VoIP. It will for instance take advantage of echo cancellation or automatic gain control if available." This is the near-end microphone, not the call.
- `REMOTE_SUBMIX` also requires `CAPTURE_AUDIO_OUTPUT`.

`core/res/AndroidManifest.xml` declares `android.permission.CAPTURE_AUDIO_OUTPUT` with `android:protectionLevel="signature|privileged|role"`. A sideloaded or Play-installed app cannot hold it; the `role` flag refers to platform roles granted by the system, not to ROLE_DIALER as far as the manifest comment states ("Allows an application to capture audio output"). `RECORD_AUDIO` is `dangerous|instant` and only grants the microphone.

The audio-sharing policy page (developer.android.com/media/platform/sharing-audio-input, retrieved 2026-10-18) states for the "voice call + ordinary app" case: "The call always receives audio." "The app can capture audio if it is an accessibility service." "The app can capture the voice call if it is a privileged (pre-installed) app with permission CAPTURE_AUDIO_OUTPUT." "To capture the voice call's uplink (TX), downlink (RX), or both, the app must specify the audio sources VOICE_UPLINK or VOICE_DOWNLINK, and/or the device AudioDeviceInfo.TYPE_TELEPHONY." An ordinary app is not in that list. Google also closed the accessibility-service loophole for third-party call recorders in Play policy from 11 May 2022 (sammobile, search summary).

Background microphone: since Android 9 "Your app cannot access the microphone or camera" while in the background; a foreground service is required (developer.android.com/about/versions/pie/android-9.0-changes-all). Since Android 14 the service must declare `foregroundServiceType="microphone"` and hold `FOREGROUND_SERVICE_MICROPHONE`; "you cannot create a microphone foreground service while your app is in the background" (while-in-use restriction) (developer.android.com/develop/background-work/services/fgs/service-types). Apps targeting Android 12+ cannot start foreground services from the background at all except for listed exemptions.

`AudioPlaybackCapture` (MediaProjection, API 29) captures only players whose usage is `USAGE_MEDIA`, `USAGE_GAME` or `USAGE_UNKNOWN`; voice-call audio is not a capturable usage (developer.android.com/media/platform/av-capture, retrieved 2026-10-18).

Samsung One UI: Samsung's US support page says call recording is available in the Samsung Phone app on devices updated to One UI 7.0 or higher (search summary of samsung.com/us/support/answer/ANS10004613, 2026-10-18); regional availability varies with local law and Samsung's 2022 supported-country list included India, but availability on the Indian Galaxy S25 firmware is UNVERIFIED. Either way the recorder is an OEM dialer feature; it writes files for the user and exposes no API to other apps.

Net result: with a consumer SIM, a third-party companion app cannot read what the gym owner says through any documented API. The only signal path is acoustic: put the call on speakerphone and record the room with `VOICE_COMMUNICATION` or `MIC`, which captures the far end only as loudspeaker leakage mixed with room noise and the phone's own echo cancellation residue.

## 3. Injecting generated speech into the uplink

There is no public API that writes PCM into the telephony uplink. `AudioTrack`/`MediaPlayer` output on `STREAM_VOICE_CALL` is routed to the local earpiece or speaker, not to the modem's TX path; during `MODE_IN_CALL` the telephony stack owns the uplink. The only path for an ordinary app is acoustic: play TTS on the loudspeaker so the handset microphone picks it up. Consequences:

- The far end hears the speaker-to-mic coupling at reduced quality, with room acoustics and the modem's noise suppression applied.
- The phone's acoustic echo canceller is tuned to cancel the far-end signal, not a local TTS source; the near-end AEC may partially suppress the TTS as if it were echo, and the local capture path (section 2) receives the TTS at full level, which drowns the far-end leakage. Full-duplex AI conversation is therefore self-interfering.
- Bluetooth: `AudioManager.startBluetoothSco()` is deprecated: "Use AudioManager#setCommunicationDevice(AudioDeviceInfo) instead"; `setSpeakerphoneOn()` is likewise deprecated. `setCommunicationDevice` notes that "MODE_IN_CALL can only be selected by the main telephony application with permission" and that priority goes to the app controlling the audio mode (media/java/android/media/AudioManager.java, retrieved 2026-10-18). A default-dialer InCallService can route the call to an HFP headset via `requestCallEndpointChange`, but HFP/SCO carries the call between phone and headset; it does not give an app access to the SCO stream. A PC acting as an HFP audio gateway or hands-free unit is a hardware/Bluetooth-stack project outside Android APIs and is UNVERIFIED for this project.
- Wired headset jack loops (phone TRRS mic in from PC audio out) are an analogue hack with no software guarantee; listed in the test matrix as `route_wired` only to document behaviour.

## 4. Wi-Fi Calling (VoWiFi / IMS)

- VoWiFi is an IMS bearer over Wi-Fi terminated in the modem/IMS stack; Telecom still presents it as a telephony `Call`, and audio still flows through the telephony audio path with `MODE_IN_CALL`. All restrictions in sections 2 and 3 are unchanged.
- Detection: a default dialer can read `Call.Details.PROPERTY_WIFI` (public). `TelephonyManager.isWifiCallingAvailable()` is `@hide` and deprecated; do not rely on it. `TelephonyManager.getVoiceNetworkType()` returning `NETWORK_TYPE_IWLAN` is a weaker public hint (UNVERIFIED in this session, not fetched).
- Jio requirements (secondary sources, 2026-10-18): a Wi-Fi-calling-capable handset on Jio's supported list, a 4G/VoLTE Jio SIM, VoLTE and Wi-Fi Calling toggles enabled in SIM settings, current firmware; Jio launched VoWiFi in January 2020 with 150+ models and the current list is at jio.com/wificalling (not retrievable here). Galaxy S25 inclusion is UNVERIFIED. Samsung community threads report the toggle disappearing when the carrier configuration is not provisioned.

## 5. Foreground services, screen lock, Samsung power management

- `phoneCall` foreground service type: requires `FOREGROUND_SERVICE_PHONE_CALL` (normal) and at runtime either `MANAGE_OWN_CALLS` in the manifest or holding `ROLE_DIALER`; Android 15+ apps cannot launch it from `BOOT_COMPLETED`. `microphone` type: requires `FOREGROUND_SERVICE_MICROPHONE` plus granted `RECORD_AUDIO`, and cannot be started while the app is in the background. Android 14 throws `MissingForegroundServiceTypeException` / `SecurityException` when types or type permissions are missing (developer.android.com/about/versions/14/changes/fgs-types-required).
- Screen locked: a foreground service keeps running, but microphone capture started before lock continues only within the while-in-use rules; starting capture after lock from a background state is not permitted. The companion must start its service while visible and before dialling.
- Samsung "Background usage limits": Sleeping apps get delayed background work; Deep sleeping apps run only when opened; Samsung's developer documentation says unused apps are moved after about 16 days (subject to change). The companion must be added to "Never sleeping apps" and excluded from adaptive battery (Samsung support and developer.samsung.com/mobile/app-management.html, search summary, 2026-10-18).

## 6. Supported alternatives for true two-way AI audio

1. VoIP/CPaaS route: SIP or WebRTC media terminates on the PC, so SELL AGENT has clean PCM in both directions and AEC under its control. In India the carrier leg must be a licensed telecom provider / registered telemarketer with 140-series (promotional) or 1600-series (service) numbers and DLT scrubbing (see docs/COMPLIANCE_INDIA.md). Android is not needed in this design; `androidx.core.telecom` is relevant only if the companion app itself hosts the VoIP call (self-managed calls use `MANAGE_OWN_CALLS`, `CallsManager`, `requestEndpointChange`, and a `phoneCall` foreground service; developer.android.com/develop/connectivity/telecom/voip-app/telecom).
2. GSM gateway hardware (SIM bank / GoIP-type) gives PCM access to a SIM-based call but is the SIMBOX usage Jio's charter prohibits and that DoT treats as illegal termination equipment when used commercially; licensing caveat UNVERIFIED in detail, treat as not an option for promotional calling.
3. Human-assisted workflow (current default): the operator dials and speaks; SELL AGENT supplies the script, eligibility gate, transcript of the operator side if desired, and outcome logging.

Release gate: `release_gate.autonomous_calling_allowed` is read-only and false; it opens only when `AudioTest` rows of kind `real_device` with `operator_confirmed=true` and `status=pass` exist for both inbound and outbound directions (`telecom/android.py: audio_gate_status`). The diagnostic APK (`apps/android-audio-diagnostic`) records what the device actually does; the expectation column below is what the documented APIs predict.

## 7. Test report template (pre-filled, NOT TESTED)

| Test ID | Date | Phone / Android / App version | Network config | Steps performed | Expected | Expected based on documented APIs | Actual | Direction | Evidence | Status | Errors / limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pairing | | S25 / Android 15 or 16 / diag 0.1.0 | LAN Wi-Fi, backend 127.0.0.1 + LAN port 8766 | Start pairing window, scan code, approve device | Token issued, heartbeat ok | PASS expected; no telephony API involved | | n/a | | NOT TESTED | |
| call_state_reporting | | | Jio VoLTE | Place manual call; observe CallStateListener events | IDLE -> OFFHOOK -> IDLE reported to backend | PASS with READ_PHONE_STATE; far-end number absent by design | | n/a | | NOT TESTED | |
| outgoing_call | | | Jio VoLTE | Backend sends call_request; app dials via ACTION_CALL/placeCall | Dialer opens and dials | PASS (CALL_PHONE); if app is default dialer, Call object states visible | | outbound | | NOT TESTED | |
| remote_speech_capture | | | Jio VoLTE, earpiece then speaker | Record with VOICE_CALL, VOICE_DOWNLINK, then VOICE_COMMUNICATION during call | Far-end speech captured | BLOCKED for third-party apps via VOICE_CALL/VOICE_DOWNLINK (CAPTURE_AUDIO_OUTPUT is signature\|privileged\|role); only acoustic speakerphone leakage via MIC/VOICE_COMMUNICATION possible, with AEC attenuation | | inbound | | NOT TESTED | |
| generated_speech_transmission | | | Jio VoLTE, speakerphone | Play Piper TTS through loudspeaker; second phone listens | Far end hears intelligible TTS | Acoustic path only; intelligible but degraded; AEC/noise suppression may clip it | | outbound | | NOT TESTED | |
| simultaneous_two_way | | | Jio VoLTE, speakerphone | TTS plays while capturing far end | Both directions usable concurrently | FAIL or DEGRADED expected: local TTS dominates the mic capture; no uplink injection API | | both | | NOT TESTED | |
| route_earpiece | | | Jio VoLTE | requestCallEndpointChange(EARPIECE) as default dialer | Route changes; capture silent | Route change PASS (default dialer only); far-end capture impossible acoustically | | both | | NOT TESTED | |
| route_speaker | | | Jio VoLTE | requestCallEndpointChange(SPEAKER) | Route changes; leakage audible | PASS for routing; this is the only route where acoustic coupling exists | | both | | NOT TESTED | |
| route_bluetooth | | | Jio VoLTE + HFP headset | Route to Bluetooth; test whether PC can act as HFP endpoint | Call audio on headset | Routing PASS; app access to SCO stream NOT available; PC-as-HFP UNVERIFIED | | both | | NOT TESTED | |
| route_wired | | | Jio VoLTE + TRRS cable to PC | Route to wired headset; feed PC audio into mic line | Analogue loop works | Analogue loop may carry audio; no software control; level/impedance issues likely | | both | | NOT TESTED | |
| latency_echo_quality | | | Jio VoLTE, speakerphone | Measure round trip TTS -> far end -> response -> STT | < 1.5 s round trip, MOS >= 3 | Latency dominated by STT/LLM/TTS on CPU; echo expected on speaker path | | both | | NOT TESTED | |
| screen_locked | | | Jio VoLTE | Lock screen mid-call with FGS running | Service and capture continue | FGS continues; microphone FGS must have started while visible; Samsung sleeping-app policy must exempt the app | | both | | NOT TESTED | |
| wifi_interruption | | | VoWiFi -> drop Wi-Fi | Disable Wi-Fi during a VoWiFi call | Handover to VoLTE; WebSocket reconnects | Call handover is carrier/IMS behaviour; app sees PROPERTY_WIFI change; backend session_reconnect | | both | | NOT TESTED | |
| hindi_phrases | | | Jio VoLTE, speakerphone | Speak 20 Hindi test phrases from far end; STT via faster-whisper small | WER < 30% | Capture limited to acoustic leakage; WER expected poor | | inbound | | NOT TESTED | |
| english_phrases | | | Jio VoLTE, speakerphone | Speak 20 English phrases | WER < 20% | Same limitation as above | | inbound | | NOT TESTED | |
| jio_wifi_calling | | | VoWiFi only (airplane mode + Wi-Fi) | Place call over Wi-Fi Calling; repeat capture tests | Same results as VoLTE | Same restrictions; PROPERTY_WIFI true for default dialer; isWifiCallingAvailable not public | | both | | NOT TESTED | Device must be on Jio's VoWiFi list (UNVERIFIED for S25) |

Evidence to attach per row: APK version hash, `adb logcat` excerpt, WAV files from both phones, backend `audio_test_result` JSON, operator signature. A row may only be marked PASS by an operator after listening to the recordings; the backend stores the result as an `AudioTest` row and the release gate recomputes.
