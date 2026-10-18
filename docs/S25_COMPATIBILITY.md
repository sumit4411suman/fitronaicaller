# Samsung Galaxy S25 (SM-S931B) compatibility audit for direct AI call audio

Status date: 2026-10-18. This audit answers one question: **can the existing Galaxy S25 on Jio give SELL AGENT
the live call's audio, in both directions, without rooting it or breaking Android security?** Short answer:
**no.** The detail and the safe checks you can run yourself are below.

## 1. What this phone is

| Fact | Value | How to confirm on the phone |
|---|---|---|
| Model | Galaxy S25, `SM-S931B` (international) | Settings > About phone > Model number |
| SoC | Snapdragon 8 Elite for Galaxy (`SM8750`) on this variant, or Exynos 2500 on some regions | `adb shell getprop ro.board.platform` and `ro.soc.model` |
| Android | Android 17 / One UI 8 (per project records) | Settings > About phone > Software information |
| SIM / voice | Jio, VoLTE / VoWiFi (Wi-Fi Calling) | Settings > Connections > SIM manager |
| Default dialer | Samsung Phone (changeable to a companion app via the dialer role) | Settings > Apps > Default apps |

Run these **read-only** `adb` commands (USB debugging on, "Allow restricted settings" granted) to record the exact
tuple — none of them change anything:

```
adb shell getprop ro.product.model
adb shell getprop ro.board.platform
adb shell getprop ro.soc.model
adb shell getprop ro.build.version.release
adb shell dumpsys telephony.registry | grep -i volte     # IMS/VoLTE registration state
adb shell cmd role get-role-holders android.app.role.DIALER
```

## 2. Why direct call audio is not possible on this phone

Android gives a live cellular/IMS call's audio to exactly three kinds of software, and this app is none of them:

1. the in-call system itself;
2. an **accessibility service** (abusing that for call capture is prohibited by the spec and by Play policy, and
   we do not do it);
3. a **privileged, pre-installed** app holding `CAPTURE_AUDIO_OUTPUT` (a `signature|privileged` permission).

Source: Android's own "Sharing audio input" guide. A normal installed app — which is all a Galaxy S25 will let
this project be — cannot capture the remote party (`VOICE_DOWNLINK`/`VOICE_CALL`) and has no public API to inject
audio into the uplink. The companion app can place the call and control routing through the dialer role; it cannot
get the audio stream.

To become a privileged app you must place the APK in a protected system partition, which on a retail phone means
**rooting / a custom system image**. On the S25 that door is also shut:

- **One UI 8 removed the OEM-unlocking toggle.** Across 2025–2026 reporting, the *OEM unlocking* option was taken
  out of Developer options on One UI 8, including on Galaxy S25-class devices, and the bootloader was observed to
  advertise a locked state with no user path to unlock. Without an unlocked bootloader there is no supported way
  to root the S25 or install a privileged component.
- Rooting, bootloader unlocking, flashing and system-partition changes are **explicitly out of scope** for this
  project, and would also void warranty, trip Knox (permanently, in hardware) and break Samsung Pay / banking.

This matches the two rooted-phone projects we evaluated (`docs/TELEPHONY_BRIDGE_EVALUATION.md`): both need Magisk
root **and** a Qualcomm `incall_music` audio path, and both list **Samsung Exynos as having no usable path at
all**. Neither targets or supports a Galaxy S25.

## 3. Verdict for the S25

| Capability needed for autonomous AI calling | On the S25 (unrooted, Jio) |
|---|---|
| Place / receive calls, read call state, route audio | **Yes** — companion app with the dialer role (human-assisted mode already uses this) |
| Capture the remote party's voice digitally | **No** — needs a privileged/system app |
| Inject AI speech into the call uplink digitally | **No** — no public API; privileged/system only |
| Become privileged without rooting | **No** — One UI 8 blocks bootloader unlock |

**The Galaxy S25 stays in human-assisted mode.** SELL AGENT listens to the operator's side, suggests the next
line, keeps the transcript and CRM, and the operator speaks. Autonomous two-way AI audio is not available on this
device by any safe, supported means.

## 4. The supported alternative (no change to this phone)

Because the S25 cannot be the audio endpoint, autonomous calling needs a **separate, qualified audio gateway** —
not a modification of the S25. The candidate architecture, how to decide between options, and the Jio
verification you must do *before buying anything* are in **`docs/CALLING_ARCHITECTURE.md`** and
**`docs/JIO_MODEM_FEASIBILITY.md`**. SELL AGENT already has the software seam for it (the media-gateway route and
AudioSocket server, `sellagent_backend/telecom/media_gateway.py` and `telecom/audiosocket.py`), still locked
behind the real-device evidence gate.
