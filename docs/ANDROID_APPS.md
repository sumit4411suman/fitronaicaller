# SELL AGENT Android apps

Two independent Android Studio / Gradle projects with the FITRON brand theme, both speaking protocol **1.0**
(`packages/shared-protocol/sellagent_protocol/messages.py`) to the local Windows backend over the LAN listener
(`https/wss://<pc-ip>:8766`).

| App | Directory | applicationId | Purpose |
| --- | --- | --- | --- |
| **Audio Feasibility Test** | `apps/android-audio-diagnostic` | `com.fitron.sellagent.audiotest` (debug: `.debug`) | Runs the 16-step audio test plan on the real Galaxy S25 and sends `audio_test.result` records. Never places campaign calls. |
| **Companion** | `apps/android-companion` | `com.fitron.sellagent.companion` (debug: `.debug`) | Human-assisted campaign calling: shows `call.request`, operator taps **Dial**, reports `call.state`, supports `call.cancel` and emergency stop. |

**Theme (approved mockups).** `brand/BrandTheme.kt` and `res/values/colors.xml` are verbatim copies of
`packages/brand/android/` (`scripts/check_brand_sync.py` passes). `SellAgentTheme(dark = true)` – gold on #0B0B0B – is
used only for the **Splash** and **Live Call** screens; `SellAgentTheme()` – off-white #F7F6F2 background, white cards
with #E6E2D6 borders, #1A1A1A text, gold #D4AF37 primary buttons with #0B0B0B text, tinted status chips – for every other
screen. Red #C62828 is used only for End Call and Emergency Stop. There is **no login, sign-up, cloud account or
billing screen**: pairing with the PC is the sign-in.

Shared code lives in each app under `app/src/main/java/com/fitron/sellagent/{protocol,brand,core}` and is
**byte-identical** between the two projects (CI diffs them). The protocol mirror also lives in
`packages/shared-protocol/kotlin/`. Both apps use the Gradle namespace `com.fitron.sellagent` so the shared code can
import a single `R` class; the application ids differ, so both install side by side.

---

## 1. Building

### Toolchain (pinned in `gradle/libs.versions.toml`)

AGP 8.7.3 · Kotlin 2.0.21 (+ Compose compiler plugin 2.0.21, serialization plugin) · compileSdk/targetSdk 35 · minSdk 29 ·
Java 17 · Compose BOM 2024.12.01 · activity-compose 1.9.3 · navigation-compose 2.8.5 · lifecycle 2.8.7 · OkHttp 4.12.0 ·
kotlinx-serialization-json 1.7.3 · kotlinx-coroutines-android 1.9.0 · security-crypto 1.1.0-alpha06 · core-ktx 1.15.0.

### Android Studio (recommended)

1. Install Android Studio Ladybug (2024.2) or newer with the Android 15 (API 35) SDK platform and build-tools 35.0.0.
2. **File ▸ Open…** and choose `apps/android-audio-diagnostic` (or `apps/android-companion`) – open the *app directory*,
   not the monorepo root. Each is a standalone Gradle project.
3. Let Gradle sync. A Gradle 8.9 wrapper (`gradlew`, `gradle/wrapper/gradle-wrapper.jar`) is committed; Studio uses it.
   If your organisation forbids committed wrapper jars, delete `gradle/wrapper/gradle-wrapper.jar` and run
   `gradle wrapper --gradle-version 8.9` once with any local Gradle 8.x to regenerate it.
4. **Build ▸ Build Bundle(s) / APK(s) ▸ Build APK(s)**. Output: `app/build/outputs/apk/debug/app-debug.apk`.

### Command line

```bash
cd apps/android-audio-diagnostic   # or apps/android-companion
./gradlew assembleDebug             # or: gradle assembleDebug  (Gradle 8.9 on PATH)
```

`ANDROID_HOME` must point at an SDK with `platforms;android-35` and `build-tools;35.0.0`.

### GitHub Actions

`.github/workflows/build-android.yml` builds both debug APKs on `ubuntu-latest` (Temurin 17, `android-actions/setup-android@v3`,
`gradle/actions/setup-gradle@v4` with Gradle 8.9) on every push / PR that touches `apps/android-**` and uploads the
artifacts **`sellagent-companion-debug.apk`** and **`sellagent-audiotest-debug.apk`**. A first job verifies that the
protocol, brand and `core` copies are identical across the projects.

### Release signing (not configured on purpose)

No keystore is committed. To ship a signed build:

1. `keytool -genkeypair -v -keystore sellagent-release.jks -alias sellagent -keyalg RSA -keysize 4096 -validity 3650`
   – keep the file outside the repository (it is git-ignored anyway: `*.jks`, `*.keystore`).
2. Put the secrets in `~/.gradle/gradle.properties` (never in the repo):
   `SELLAGENT_STORE_FILE=/abs/path/sellagent-release.jks`, `SELLAGENT_STORE_PASSWORD=…`, `SELLAGENT_KEY_ALIAS=sellagent`, `SELLAGENT_KEY_PASSWORD=…`.
3. In `app/build.gradle.kts` add a `signingConfigs { create("release") { … read those properties … } }` block and
   `buildTypes.release.signingConfig = signingConfigs.getByName("release")`, then `./gradlew assembleRelease`.
4. For CI, store the base64-encoded keystore and the passwords as GitHub Actions secrets and decode them into a temp file
   in a step before `assembleRelease`.

---

## 2. Installing on the Samsung Galaxy S25

1. **Settings ▸ About phone ▸ Software information** – tap *Build number* 7× to enable Developer options.
2. **Settings ▸ Developer options** – enable *USB debugging* (and *Install via USB* if shown).
3. Connect the phone, accept the RSA prompt, then:
   ```bash
   adb install -r sellagent-audiotest-debug.apk
   adb install -r sellagent-companion-debug.apk
   ```
   (or copy the APKs to the phone and open them; allow *Install unknown apps* for My Files when asked.)
4. Both apps appear with the FITRON gold mark: **SELL AGENT Audio Test** and **SELL AGENT Companion**.
5. Make sure the phone and the Windows PC are on the **same Wi-Fi network** and that Windows Firewall allows inbound
   TCP 8766 for the backend (the Windows app opens this when the LAN listener is enabled).

---

## 3. Permissions

### Manifest – Audio Feasibility Test

`INTERNET`, `ACCESS_NETWORK_STATE`, `CALL_PHONE`\*, `READ_PHONE_STATE`\*, `RECORD_AUDIO`\*, `MODIFY_AUDIO_SETTINGS`,
`POST_NOTIFICATIONS`\*, `BLUETOOTH_CONNECT`\*, `FOREGROUND_SERVICE`, `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`, `FOREGROUND_SERVICE_PHONE_CALL`,
`FOREGROUND_SERVICE_MICROPHONE`, `FOREGROUND_SERVICE_DATA_SYNC`.
Services: `SellAgentInCallService` (`BIND_INCALL_SERVICE`, `IN_CALL_SERVICE_UI=true`),
`ConnectionForegroundService` (`foregroundServiceType="phoneCall|microphone|dataSync"`).

### Manifest – Companion

`INTERNET`, `ACCESS_NETWORK_STATE`, `CALL_PHONE`\*, `READ_PHONE_STATE`\*, `RECORD_AUDIO`\*, `MODIFY_AUDIO_SETTINGS`,
`POST_NOTIFICATIONS`\*, `BLUETOOTH_CONNECT`\*, `FOREGROUND_SERVICE`, `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`, `FOREGROUND_SERVICE_PHONE_CALL`,
`FOREGROUND_SERVICE_DATA_SYNC`.
Services: `SellAgentInCallService` (as above), `ConnectionForegroundService` (`foregroundServiceType="phoneCall|dataSync"`).

\* runtime permission requested from the *Permissions* screen.

### Battery optimization

`REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` lets the *Battery optimization* screen open the system dialog
`Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` (`package:` URI), with `ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS`
as fallback. **Google Play restricts this permission for store apps; these apps are sideloaded onto one operator phone,
which is the permitted use.** The state shown everywhere (Battery screen, Permissions row, Diagnostics "Run full test",
Troubleshooting) is the real `PowerManager.isIgnoringBatteryOptimizations(packageName)`, and every heartbeat/capabilities
message carries it in `DeviceCapabilities.notes` as `battery_optimization_ignored=true|false|unknown`.
Samsung additionally puts apps to sleep: **Settings › Battery › Background usage limits › Never sleeping apps › add
SELL AGENT**, and set the app's Battery to *Unrestricted* (the screen has a button to the app's App info page,
`ACTION_APPLICATION_DETAILS_SETTINGS`).

### Default dialer role

Both apps can request **RoleManager.ROLE_DIALER**. This is the only supported way for an app to receive an
`InCallService` binding, which is in turn the only supported way to observe detailed call states
(`Call.STATE_DIALING/RINGING/ACTIVE/HOLDING/DISCONNECTED` with a `DisconnectCause`), to change the audio route
(`InCallService.setAudioRoute`) and to end a call (`Call.disconnect`). Without the role the apps fall back to
`TelephonyCallback.CallStateListener` (IDLE/RINGING/OFFHOOK only) and `AudioManager.setCommunicationDevice`, and they
**cannot** end a call – the UI then shows "Hang up now". The role can be handed back to *Samsung Phone* at any time
from **Settings ▸ Apps ▸ Default apps ▸ Phone app**.

### How each capability flag is derived (`DeviceCapabilities`)

| Flag | Set to `true` only when | API |
| --- | --- | --- |
| `can_place_calls` | `CALL_PHONE` granted | `ContextCompat.checkSelfPermission` |
| `reports_call_state` | `READ_PHONE_STATE` granted **and** a `TelephonyCallback` is registered right now | `TelephonyManager.registerTelephonyCallback` (API 31+) / `PhoneStateListener` (29–30) |
| `is_default_dialer` | role held | `RoleManager.isRoleHeld(ROLE_DIALER)` |
| `can_control_audio_route` | our `InCallService` is bound | `InCallService.onBind` |
| `can_end_calls` | our `InCallService` is bound | `Call.disconnect()` |
| `supports_foreground_service` | `startForeground` succeeded in this process | `ServiceCompat.startForeground` |
| `remote_audio_capture_verified` | **never** (always `false` from the app) | backend sets it from confirmed test records |
| `audio_injection_verified` | **never** (always `false` from the app) | backend sets it from confirmed test records |
| `wifi_calling_active` | `true`/`false` **only during a call observed by our InCallService** (default dialer), from that call's `Call.Details.PROPERTY_WIFI`; otherwise `null` | `Call.Details.hasProperty(PROPERTY_WIFI)`. `TelephonyManager.isWifiCallingAvailable` is hidden and `ImsMmTelManager` is system-only, so outside such a call the UI says "Unknown (no public API)" |

---

## 4. Security model

* **TLS pinning.** The backend's LAN listener uses a self-signed certificate; the Windows pairing screen shows its
  SHA-256 fingerprint (`AA:BB:…`). The operator types it into the app. `FingerprintTrust.PinnedTrustManager` accepts the
  server **only if `SHA-256(DER(leaf))` equals that fingerprint**; no CA store is consulted and nothing is accepted
  otherwise. Hostname verification runs the platform RFC 2818 check first and, because the certificate's SANs only
  list `localhost`/`127.0.0.1`, falls back to "the presented certificate is the pinned one". Both are installed on
  the single OkHttpClient used for the backend, never globally. Regenerating the certificate on the PC requires re-pairing.
* **Secrets.** Device token, pinned fingerprint and device id are stored in `EncryptedSharedPreferences`
  (AES256-SIV keys / AES256-GCM values) under an Android Keystore master key. They are excluded from backups and
  device transfer (`res/xml/data_extraction_rules.xml`). The token is never shown, logged or put in a URL; it is sent
  only as `Authorization: Bearer` to the pinned host.
* **No privileged tricks.** Only public SDK APIs are used: no reflection, no hidden APIs, no accessibility service,
  no root. The apps cannot and do not capture the remote party's audio or inject audio into the uplink (see §7).

---

## 5. Wire protocol behaviour

* Every message is an `Envelope {protocol_version:"1.0", type, message_id (uuid hex), sent_at (ISO-8601 UTC), in_reply_to?, payload}`;
  Kotlin data classes in `protocol/Protocol.kt` carry explicit `@SerialName`s that match `messages.py`.
* **Pairing:** `POST /api/v1/devices/pair` → poll `GET /api/v1/devices/pair/result?device_public_id=…` every 2 s (max 5 min)
  → on `approved` the one-time `device_token`, `device_id`, `backend_name`, `ws_path` are stored.
* **Session:** `wss://<pc>:8766/api/v1/ws/device` with the bearer header. On every (re)connect the app sends
  `session.reconnect {device_id, last_received_message_id, pending_events}` and then replays its file-backed outbox
  (`files/outbox.jsonl`). Durable envelopes (`call.state`, `audio_test.result`, `session.capabilities`,
  `safety.emergency_stop`) stay in the outbox until an `ack`/`error` with a matching `in_reply_to` arrives.
* **Heartbeat** every 20 s: `session.heartbeat {device_id, battery_percent, network, wifi_calling_active, in_call, capabilities}`
  (`wifi_calling_active` is null unless observed via `PROPERTY_WIFI`, see §3).
  `session.heartbeat_ack.emergency_stop_active` and `session.reconnect_ack.emergency_stop_active` drive the local
  emergency-stop latch (the only way the latch is cleared is the PC reporting `false`).
* **Inbound de-duplication** by `message_id` (LRU of 2000). A duplicate `call.request` is re-acked, not re-shown.
* **Acks:** the backend awaits a reply only for `call.request`; the Companion replies `ack {message_id}` with
  `in_reply_to` when it accepted the request for operator confirmation, or `error {code, message}` otherwise.
  The diagnostic app always replies `error code=diagnostic_app`. `call.cancel` and `safety.emergency_stop` are
  confirmed through `call.state` events / `safety.emergency_stop` (`issued_by=android`) respectively.
* **Forward compatibility:** `MessageType.KNOWN` lists every type this build understands, including the generic
  `event` envelope (`payload {name, data}`) used for desktop notifications, which is logged and never acked. Any other
  unknown `type` is logged ("ignored unknown message type") and ignored – no ack, no error, no exception. Unknown payload
  fields are ignored (`ignoreUnknownKeys`); malformed JSON is dropped via `Envelope.parseOrNull`.
* **Backoff:** 1, 2, 4, 8, 16, 32, 60 s (+0–1 s jitter), reset after a successful connection.

---

## 6. Screens

Both apps start with a dark **Splash** (gold FITRON mark, "SELL AGENT" with "AGENT" in gold, subtitle *Local AI calling
for FITRON sales*, chips Smart / Secure / Local) and, on first launch, a three-page light **Onboarding** with *Skip*
(what the app does · permissions overview · pairing explained; no account). Shared screens (identical code in both apps):

| Shared screen | What it shows / does |
| --- | --- |
| **Device Connection** (pairing) | "Connected to PC" / "Not connected" banner, phone model + Android version, Wi-Fi state, battery, Wi-Fi calling (Active / Not on this call / Unknown), app version, device id, endpoint, pinned fingerprint, *Reconnect*, red outlined **Disconnect** (forgets the token). When unpaired: PC IP, port 8766, pairing code, TLS fingerprint form. Form survives rotation/process death (`SavedStateHandle`). |
| **Permissions** | One row per permission with reason and a *Granted* chip or gold *Request* button, plus the default-dialer role row; foreground-service *Start & verify*; derived `DeviceCapabilities` with the API behind each flag; *Send session.capabilities*; "What a normal app cannot do". |
| **Diagnostics** | Rows Microphone (3-s `AudioRecord(VOICE_COMMUNICATION)` RMS dBFS, labelled near-end), Speaker (1 kHz `AudioTrack` tone accepted?), Wi-Fi calling (PROPERTY_WIFI or unknown), Audio route (current), Network latency (median of 3 pinned HTTPS pings to the PC). Gold **Run full test** runs this short self-check; values read "Not run" until measured. |
| **Live Call** (dark) | Gold timer (from InCallService `STATE_ACTIVE`, else from the OFFHOOK transition), state label (InCallService or TelephonyCallback name), *Human-assisted* chip, route and Wi-Fi-calling chips, local notes area with the statement that no transcript exists (apps cannot access call audio), Mute / Hold / Keypad (`InCallService.setMuted`, `Call.hold/unhold`, `Call.playDtmfTone`) enabled only when InCallService is bound – otherwise disabled with an explanation, red **End call**, Emergency stop. |
| **Help & Support / About** | Condensed operator help from this document; version, protocol 1.0, device, "no account" statement. |

### Shared support screens (both apps)

| Screen | What it does |
| --- | --- |
| **Battery optimization** | Real `isIgnoringBatteryOptimizations` state, *Allow unrestricted* (request dialog) / *Open battery settings* (fallback), battery %, Samsung "Never sleeping apps" card with an *Open App info* button. |
| **Logs** | `AppLog`: last 1000 entries in memory plus `files/logs/app.log` (rotated to `app.log.1` at 256 KB). Connection, pairing, permission, call.state, InCallService/TelephonyCallback, emergency-stop, test and error events. Filter by minimum level (DEBUG/INFO/WARN/ERROR), *Share as text* (share sheet, with device/app header), *Clear*. Every message is sanitized: bearer tokens, `token=`/`authorization` values, long hex/secret strings and certificate fingerprints become `[redacted]`/`[fingerprint]`; phone numbers are masked to the last 4 digits (`…3210`). |
| **Troubleshooting** | Live checks with fixes: connection (backend address + last WebSocket error → Reconnect / Pair), TLS certificate mismatch (→ Pair again), missing runtime permissions (→ Permissions), not default phone app (→ Permissions), battery optimization on (→ Battery), Wi-Fi off (→ Wi-Fi settings), emergency stop active (cleared only on the PC). *Check again*, link to Logs. |
| **Microphone test** | 3 s `AudioRecord(VOICE_COMMUNICATION)`; live level bar, RMS and peak dBFS, quiet/clipping hints. Near-end microphone only. |
| **Speaker test** | 1 kHz `AudioTrack` tone, then one Hindi and one English `TextToSpeech` phrase on the current output; the operator answers *Did you hear it?* Yes/No (logged). |
| **Audio route** | Current route, `AudioManager.mode`, communication device, `getAvailableCommunicationDevices()` (API 31+), `getDevices(GET_DEVICES_OUTPUTS)`, supported routes for the current call (`CallAudioState.supportedRouteMask`, InCallService only), route buttons that report the API used. |

Diagnostics links to all six. Companion: **More** lists Mic test, Speaker test, Audio route, Battery optimization,
Troubleshooting and Logs. Audio test: the **Report** tab has a *Troubleshooting & tools* card with all of them.

### Companion (bottom navigation: Home · Contacts · Campaigns · Calls · More; gold active icon)

| Screen | What it does |
| --- | --- |
| **Home** | Logo header + settings gear; connection chip + *Human-assisted* chip; **Ready for Calls** card with real heartbeat facts (network/Wi-Fi, Wi-Fi calling, battery, last heartbeat ack, requests waiting); round **Dial** (green; enabled only when a `call.request` is queued, dials the oldest), **End** (red; InCallService only), **Speaker** (route toggle; in a call only). Tiles: Call Queue, Diagnostics, Permissions, Settings, Call Logs, Help. **Current Call Status** card: mode *Human-assisted*, job id, TelephonyCallback state, InCallService state – never an "AI speaking" label. |
| **Contacts / Campaigns** | Read-only empty state *"Managed on the PC"* with the connection status. Protocol 1.0 has no device contacts/campaign API, so nothing is invented. |
| **Calls › Call Queue** | Every queued `call.request` (up to 10) with number, display name, mode, language, requested route, expiry countdown, job id, **Dial** / **Decline** per row. **Pause queue** switch: while on, new requests are refused with `error queue_paused`. |
| **Calls › Call Logs** | Local history per `call_job_id` built from the `call.state` events this phone sent (final state chip, duration measured on the phone from first ACTIVE/OFFHOOK to end). Persisted in `files/call_logs.json`; *Clear local history*. |
| **Calls › Call Summary** | Job id, number, display name, mode, duration, final state, state-event list, **Add note** – notes stay on this phone in this release (labelled so; nothing in protocol 1.0 carries them). |
| **More** | Device Connection, Diagnostics, Permissions, Settings, Help & Support, About, red **Emergency Stop** entry. |
| **Emergency Stop** | Large red button: sends `safety.emergency_stop (issued_by=android)`, ends the call if bound (else "Hang up now"), rejects all queued requests, blocks dialing until `heartbeat_ack.emergency_stop_active=false`. |
| **Settings** | Calling mode (human-assisted, fixed on; autonomous *Disabled on device*), endpoint, unsent events, reconnect, Disconnect, About. |
| **Live Call** | Opens automatically when the operator dials a job and closes when the job ends (see shared table). |

Refusals sent as `error` envelopes (each mirrored as `call.state rejected`): `emergency_stop_active`, `autonomous_disabled`
("autonomous mode not enabled on device"), `unsupported_mode`, `invalid_expiry`, `expired`, `invalid_authorization`,
`call_phone_not_granted`, `queue_paused`, `duplicate_job`, `queue_full`, `invalid_call_request`.

### Audio Feasibility Test (bottom navigation: Pairing · Permissions · Tests · Call · Report)

| Tab | What it does |
| --- | --- |
| **Pairing** | The shared Device Connection screen. |
| **Permissions** | The shared Permissions screen. |
| **Tests** (light) | *Start new run* creates `AFT-yyyyMMdd-HHmm`. The 16 steps use the exact backend `step` ids. Each card: instruction, automatic tool, live metric, observation, **Pass / Fail / Blocked / Not tested** (each sends `audio_test.result` with `test_id, step, direction, status, route, api_used, error_message, metrics, evidence`). Network-config note, unsent counter, **EMERGENCY STOP**. |
| **Call** | Light dial screen when idle (E.164 number → `TelecomManager.placeCall`, coarse/detailed state, route buttons). **During an active call it switches to the dark Live Call screen** with the diagnostic route buttons and *Save note to timeline*. |
| **Report** (light) | Test ID, date, device model, Android version, app version, network note, per-step status/api/metrics/evidence/errors, timeline; share as text or JSON. Banner: *"Simulated or emulator results are not evidence. Autonomous AI calling remains disabled until the backend's release gate is opened from operator-confirmed real-device results."* |

Automatic tools per step:

| Step | Tool | Measures / records |
| --- | --- | --- |
| `pairing` | connection evidence | socket state, backend, endpoint, pinned fingerprint, network, heartbeat acks |
| `call_state_reporting` | state evidence | TelephonyCallback/InCallService registration + timeline of state changes |
| `outgoing_call` | dial evidence | last states, `placeCall` log lines |
| `remote_speech_capture` | probe + mic meter | tries `AudioRecord(VOICE_DOWNLINK/VOICE_CALL/VOICE_UPLINK)` and records the platform's refusal; the 5-s mic meter is labelled **near-end microphone, NOT remote party audio** |
| `generated_speech_transmission` | TTS | Hindi + English fixed phrases via `TextToSpeech` with `USAGE_VOICE_COMMUNICATION`; engine, language availability, route; path is acoustic |
| `simultaneous_two_way` | TTS ‖ mic meter | both at once (12 s) |
| `route_*` | switch / read | `InCallService.setAudioRoute` when default dialer, else `AudioManager.setCommunicationDevice`; `api_used`, route before/after |
| `latency_echo_quality` | acoustic loopback | 150 ms chirp via `AudioTrack`, recorded with `AudioRecord(VOICE_RECOGNITION)`, cross-correlated → latency, correlation, noise floor (labelled *acoustic loopback*) |
| `screen_locked` | 60-s lock test | foreground service + counts of heartbeat acks / disconnects / telephony callbacks while locked |
| `wifi_interruption` | reconnection evidence | reconnects, disconnects, max backoff, unsent results, transport log |
| `hindi_phrases` / `english_phrases` | TTS | the fixed phrase sets |
| `jio_wifi_calling` | network evidence | network transport, route, operator note; VoWiFi from PROPERTY_WIFI during a call, otherwise *unknown* |

---

## 7. Known limitations (by Android design)

* `MediaRecorder.AudioSource.VOICE_CALL`, `VOICE_DOWNLINK`, `VOICE_UPLINK` require `CAPTURE_AUDIO_OUTPUT`, a
  signature/privileged permission. A sideloaded app cannot obtain it; the diagnostic probe documents the failure.
* `AudioPlaybackCapture` excludes `USAGE_VOICE_COMMUNICATION` audio, so it cannot capture the far end either.
* There is **no public API to inject audio into the cellular / VoWiFi uplink**. The only path is acoustic: TTS through
  the loudspeaker picked up by the phone's microphone, with the quality and echo-cancellation artefacts that implies.
* `TelephonyManager.isWifiCallingAvailable` is not in the public SDK. VoWiFi is known only per call, from
  `Call.Details.PROPERTY_WIFI`, while the app is the default dialer; otherwise it is `null`/unknown and must be read
  from the status bar by the operator.
* `InCallService` is bound only while the app is the default dialer. Without the role: coarse states only, no
  programmatic hang-up, route changes through `AudioManager` may be overridden by the Samsung dialer.
* Android 14+ foreground-service rules: `phoneCall` type needs the dialer role; `microphone` type needs
  `RECORD_AUDIO` and a foreground start; otherwise the service falls back to `dataSync` (Android 15 caps it at 6 h/day).
  The *Permissions* screen shows which type is actually in use.
* The autonomous release gate flag is not pushed to the device yet; `mode=autonomous` is always refused.
* The release gate on the PC is opened only from operator-confirmed **real-device** `audio_test.result` rows. The
  apps never set `remote_audio_capture_verified` / `audio_injection_verified`.
* Samsung's "Never sleeping apps" list cannot be changed by an app; the operator must set it (the Battery screen explains how).
* Contacts and Campaigns are not sent to the phone in protocol 1.0; the Companion tabs are empty "Managed on the PC" views.
* Call notes stay on the phone (protocol 1.0 has no message for them).
* Build status: these projects were written in an environment without the Android SDK. The pure-Kotlin parts
  (protocol serialization including unknown-type/`event` tolerance, outbox, fingerprint pinning, AppLog sanitization
  and ring buffer) were compiled and unit-tested on the JVM; the Android parts are
  first compiled by the CI workflow / Android Studio sync.

---

## 8. Manual test procedure on the Galaxy S25 (Jio SIM)

Preparation (once):

0. In each app open *Battery optimization* → *Allow unrestricted*, then *Open App info* → Battery → Unrestricted, and
   add SELL AGENT under Settings › Battery › Background usage limits › Never sleeping apps.

1. Start the Windows app, enable the LAN listener, open **Devices ▸ Pair**. Note the IP, port 8766, pairing code and
   the SHA-256 fingerprint.
2. Install both APKs (§2). Open **SELL AGENT Audio Test**.
3. *Pairing* tab: type IP, port, code, fingerprint → **Pair** → approve on Windows → state becomes *Connected to SELL AGENT*.
4. *Permissions* tab: **Request permissions** (allow all five), **Request default dialer** (confirm the system dialog),
   **Start & verify** the foreground service, then **Send session.capabilities**. All derived flags except the two
   *never set by the app* ones and `wifi_calling_active` should now read *Yes*.
5. Have a second phone (the "far end") with a known number, in a different room.

Test run:

1. *Tests* tab → enter the network note (e.g. `Wi-Fi "FITRON-5G", Jio SIM 1, VoWiFi off`) → **Start new run**. Note the Test ID.
2. **pairing** → *Record connection evidence* → Pass.
3. *Call* tab → enter the far-end number in E.164 → **Dial**; answer on the far end, talk 10 s, **End call** (or hang up
   on the far end). Back on *Tests*: **call_state_reporting** → *Record call-state evidence* → check the timeline shows
   `STATE_DIALING → STATE_ACTIVE → STATE_DISCONNECTED` (InCallService) and `OFFHOOK → IDLE` (TelephonyCallback) → Pass/Fail.
4. **outgoing_call** → *Record dial evidence* → Pass if the far end rang and answered.
5. Dial again and keep the call up for steps 6–12.
6. **remote_speech_capture** → far end speaks → *Probe VOICE_CALL / DOWNLINK / UPLINK* (expect "not available"),
   *Measure near-end mic* → mark **Blocked** (unless the probe unexpectedly succeeded – then verify and describe).
7. **generated_speech_transmission** → switch to speaker (step 8 button or Call tab) → *Speak test phrases* → ask the far
   end what they heard → write it down → Pass/Fail.
8. **route_speaker**, then **route_earpiece** → *Switch route* → confirm by ear on both ends → Pass/Fail; note `api_used`.
9. **route_bluetooth** → pair a BT headset first, *Switch route* → Pass/Fail/Blocked.
10. **route_wired** → plug a USB-C headset, *Read current route* → Pass/Fail/Blocked.
11. **simultaneous_two_way** → *Speak + measure mic at once* while the far end talks → note whether either side was muted.
12. **hindi_phrases** / **english_phrases** → play each set → far end repeats → Pass/Fail with observation.
13. **latency_echo_quality** → end the call, media volume ≥ 70 %, quiet room → *Acoustic loopback (chirp)* → expect a
    latency value with correlation > 0.15; during a call also write the far end's echo/clipping remarks.
14. **screen_locked** → *Start 60 s lock test* → lock the phone immediately → unlock after a minute → Pass if ≥ 2
    heartbeat acks and 0 disconnects.
15. **wifi_interruption** → turn Wi-Fi off for 20 s, then on → watch *Pairing* tab show backoff then *Connected* and the
    unsent counter return to 0 → press **EMERGENCY STOP** once, clear it on the PC → *Record reconnection evidence* → Pass/Fail.
16. **jio_wifi_calling** → enable Wi-Fi Calling in Settings ▸ Connections ▸ Wi-Fi Calling, confirm the status-bar icon,
    repeat a call and one route switch → *Record network evidence* → Pass/Fail; write the icon state in the observation.
17. *Report* tab → **Share text** / **Share JSON** to the PC owner. On Windows, confirm each real-device row; only confirmed
    PASS rows feed the release gate.

Companion check (after the diagnostic run):

1. Open **SELL AGENT Companion**, pair it (new pairing code on Windows), grant permissions, request the dialer role.
2. From Windows dispatch a human-assisted call job to this device. *Calls › Call Queue* shows the row and the *Calls*
   tab label shows the count. Tap **Dial** within the expiry (or the green Dial on Home) → the dark Live Call screen
   opens → Windows receives `requested/dialing/active/disconnected`. Check *Call Logs* and *Call Summary* afterwards.
   Turn on **Pause queue**, dispatch again and confirm Windows reports `queue_paused`; turn it off.
3. Dispatch another job and press **Cancel** on Windows: with the dialer role the call ends by itself; without it the
   red "HANG UP NOW" banner appears.
4. Dispatch a job with `mode=autonomous`: it must be refused with "autonomous mode not enabled on device".
5. Press **More › Emergency Stop** on the phone: Windows cancels all jobs; the phone refuses new requests until you clear the
   stop on Windows and the next heartbeat ack reports it cleared.
