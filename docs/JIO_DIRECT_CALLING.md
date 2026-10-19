# SELL AGENT — direct Jio calling with your Galaxy S25 (no paid telephony provider)

Status date: 2026-10-19. Goal of this document: answer, honestly and with checks you can run yourself, whether
your existing **Samsung Galaxy S25 (SM-S931B) on Jio**, controlled from **Windows over a USB cable**, can give
SELL AGENT a **two-way AI phone call** (Priya hears the gym owner and speaks back into the same live call) — with
**no Exotel, no Twilio, no paid AI/speech/telephony API**.

This replaces Exotel as the *required* path. Exotel is now an **optional** cloud add-on only (see the bottom
section); nothing in the app needs it to run.

## TL;DR

| Question | Answer |
|---|---|
| Can Windows dial through the phone over USB? | **Yes** — `adb` CALL intent, or the companion app. Proven by the diagnostic below. |
| Can the AI read genuine call-state (ringing/active/ended)? | **Yes** — coarse via ADB; detailed via the companion app's InCallService. |
| Can the AI capture the **remote person's actual voice** over USB? | **No** — ADB exposes no call-audio stream; that capture is privileged-only. |
| Can the AI inject **Priya's voice** into the same call over USB? | **No** — no public uplink-injection API on a non-rooted phone. |
| Both directions at once, over USB only? | **No** — follows from the two above. |
| Is there *any* no-subscription way to get the audio? | **Yes, but not over USB data** — a physical audio route (Bluetooth HFP, or a wired USB‑C DAC + TRRS splitter). Both need either a capability your PC may lack or a small hardware purchase, which needs your approval. |

So: **the campaign control loop works today on your own phone and SIM** (import → dial → call-state → outcome →
next contact → pause/stop), in **human-assisted mode**. **Autonomous two-way AI audio stays disabled** until a
real, supported audio path is proven on your device. This is not a limitation we chose — it is Android's call-audio
security model on a non-rooted phone.

## 1. Prove it yourself (USB ADB diagnostic)

On the Windows PC, with the S25 on a USB cable, USB debugging ON, and "Allow restricted settings" granted:

```
# device facts + current call state + the honest audio verdict
python scripts/adb_jio_diagnostic.py --out jio_evidence.json

# place ONE real call to a CONSENTING participant and watch the state change
python scripts/adb_jio_diagnostic.py --dial +91XXXXXXXXXX --consent

# hang up (this is the Stop / Emergency-Stop primitive)
python scripts/adb_jio_diagnostic.py --endcall
```

What it checks, separately, matching the spec:

- **initiate calls on the Jio SIM** → `--dial` places a standard CALL intent; the SIM/VoLTE/carrier place the call
  exactly as a manual dial. The report shows the call-state transition as proof the dial reached telephony.
- **genuine call-state events** → `--state` reads `mCallState` (IDLE/RINGING/IN_CALL). The companion app adds the
  finer InCallService timeline.
- **remote voice into the AI** / **AI voice into the call** / **both directions** → `--audio` reports the verdict:
  **not available over ADB**, with the exact reason. The tool never fakes a pass; a successful dial is control, not
  audio.
- **survives interruption / lock / cancel / network change** → call-state reads and `--endcall` keep working while
  the screen is locked and across data changes; the companion app's foreground service and InCallService are what
  make this robust during a live call.

The pure command-building and parsing logic is unit-tested headless (`tests/unit/test_adb.py`); the subprocess
runner is `scripts/adb_jio_diagnostic.py`. **Running it on your S25 is the only way to produce real device
evidence — this repository does not and must not ship fabricated device results.**

## 2. Why USB ADB cannot carry the call audio (the precise blocker)

Android hands a live cellular/IMS call's audio to only three kinds of software: the in-call system itself; an
accessibility service (prohibited for this use by spec and Play policy — we do not do it); or a **privileged,
pre-installed** app holding `CAPTURE_AUDIO_OUTPUT` (a `signature|privileged` permission). A normal app — all a
retail S25 will let this project be — **cannot** read `VOICE_DOWNLINK`/`VOICE_CALL` and has **no public API** to
inject into the uplink. (Source: Android "Sharing audio input" guide.)

ADB does not change this. ADB is a control and debugging channel:

- There is **no `adb` command that exposes the modem/voice-call PCM** to the shell or to the PC.
- **scrcpy's** audio forwarding (Android 11+) relies on `AudioPlaybackCapture`, which **excludes voice-call
  audio**; scrcpy cannot capture the call. Mirroring the screen does not mirror the call's voice path.
- Granting the app *more* permissions does not help — the missing permission is `signature|privileged`, which a
  user cannot grant.

Becoming a privileged app means placing the APK in a protected system partition, i.e. **rooting / a custom system
image**. On the S25 that door is shut: **One UI 8 removed the OEM-unlocking toggle**, so the bootloader cannot be
unlocked, so the S25 cannot be rooted by any supported means. Rooting/flashing is out of scope anyway (it voids
warranty, trips Knox in hardware, and breaks banking/Samsung Pay). Full device audit: `docs/S25_COMPATIBILITY.md`.

## 3. SIMVox-AI evaluation (the project you pointed to)

`https://github.com/Magraa/SIMVox-AI` (MIT licence). It targets the same idea — an Android phone + SIM as an AI
voice agent driven from a PC over ADB — so it is a fair reference. What it actually does, and how it bears on your
constraints:

| Aspect | SIMVox-AI | Fit with your requirements |
|---|---|---|
| Call control | ADB "Telephony Controller" over USB/Wi-Fi (dial, auto-answer) | ✅ Same supported path we use. Reusable idea; our `telecom/adb.py` does the equivalent. |
| LLM | **Google Gemini (cloud)** | ❌ You require local AI. We keep faster-whisper + local conversation engine + Piper; no cloud LLM. |
| TTS | **Microsoft Edge neural TTS (cloud)** | ❌ Cloud. We use local female Piper (hi/en). |
| **Call audio** | **Bluetooth HFP**, **3.5 mm AUX + TRRS splitter**, or a **PC virtual audio cable** (VB-Cable/VoiceMeeter) | ⚠️ **None of these is a digital USB capture of the call.** They are *physical audio routes*. See below. |
| Licence | MIT | ✅ Compatible to borrow ideas/snippets with attribution. |

The decisive point: **SIMVox-AI does not solve the audio blocker — it routes around it with external audio
hardware/paths, exactly as Section 2 predicts.** Its three options are:

1. **Bluetooth HFP** — the PC acts as the phone's hands-free unit; the call's two-way audio rides the Bluetooth
   SCO link. This is a *real* two-way path **when the PC can be an HFP unit**. On your specific Windows PC this was
   observed to work in an earlier test, but standard desktop Windows often cannot expose that role, and **you asked
   to avoid Bluetooth**.
2. **3.5 mm AUX + TRRS splitter** — analog line audio in/out of the headset jack. **The S25 has no 3.5 mm jack**,
   so this needs a **USB‑C → 3.5 mm headset DAC** plus a **TRRS splitter** plus a **PC line-in** (most laptops lack
   one, so also a cheap USB sound card). It is wired and low-latency, but it is **analog line level, not a digital
   USB-data stream**, and it **requires hardware**.
3. **Virtual audio cable** — this is **PC-internal routing only**. It cannot pull audio out of the phone's call by
   itself; the call audio must already be on the PC via (1) or (2). On its own it proves nothing.

The “virtual audio cable” being listed alongside the others can mislead: it is not an independent way to get the
call off the phone. Treat SIMVox-AI's working audio as **(1) or (2)**, i.e. Bluetooth or added wired hardware.

## 4. The supported, no-subscription options (your choice; no purchase without your OK)

Given "prefer wired, no Bluetooth", the honest ranking for keeping your Jio number and paying no subscription:

1. **Human-assisted on the S25 (works now, zero hardware).** Windows dials through the phone; you speak; Priya
   runs STT→reply suggestions→transcript locally and keeps the CRM/outcomes/follow-ups. This is the default and is
   not gated.
2. **Wired analog bridge (needs ~₹500–₹1500 of hardware, needs your approval).** USB‑C headset DAC on the S25 +
   TRRS splitter + USB audio-in on the PC. Carries both directions as analog line audio into SELL AGENT's existing
   local-audio media-gateway seam (`telecom/local_audio.py`). This is the wired route you asked about; it is
   feasible but it is **not pure-USB data** and it **requires buying the adapters first**. I will not purchase or
   assume anything — tell me to proceed and I'll document the exact parts and wiring.
3. **Bluetooth HFP (zero hardware if your PC supports the HFP unit role).** Proven to work on your PC before, but
   you prefer to avoid it. Kept available (`docs/BLUETOOTH_AUDIO.md`, `scripts/run_priya_bluetooth.py`).

A separate USB cellular modem + Asterisk is the other no-cloud autonomous option but it is a *different* SIM/number
and needs Jio VoLTE verification before any purchase (`docs/JIO_MODEM_FEASIBILITY.md`) — out of scope for "use my
existing phone."

### How the audio bridge actually makes Priya two-way

The point both options share: you do **not** need the forbidden digital stream. You route the **call's audio into
the PC's sound system**, and SELL AGENT's local loop already reads a PC input and writes a PC output
(`telecom/local_audio.py`, `SipRtpCallAudioPath`, run by `scripts/run_priya_bluetooth.py`). The resolver accepts
one combined device (Bluetooth) **or two separate devices** (wired), so the same AI runs over either:

```
# Bluetooth HFP (one hands-free device, verified on this PC):
python scripts/run_priya_bluetooth.py --consent --match "HF Audio" --contact "Rahul" --business "Power Gym"

# WIRED, no Bluetooth (two separate PC devices):
python scripts/run_priya_bluetooth.py --list-devices          # find the two device names first
python scripts/run_priya_bluetooth.py --consent --input "Line In" --output "USB-C DAC" --contact "Rahul"
```

**Wired parts (only if you choose wired — I will not buy anything without your OK):**

| Part | Why | Rough cost |
|---|---|---|
| USB‑C → 3.5 mm **headset** adapter (CTIA, 4‑pole) | The S25 has no 3.5 mm jack; this exposes the call's earpiece-out **and** mic-in as analog | ₹150–400 |
| TRRS (4‑pole) → 2× TRS splitter ("headset splitter") | Separates that one 4‑pole plug into a headphone plug and a mic plug | ₹150–300 |
| USB external sound card with **mic/line-in + headphone-out** | Most laptops have no line-in; this gives the PC both directions | ₹300–800 |
| 2× 3.5 mm patch cables | Cross-wire the two sides | ₹100 |

**Cross-wiring (the part that matters):** phone **earpiece-out → PC mic/line-in** (so Priya hears the caller), and
PC **headphone-out → phone mic-in** (so the caller hears Priya). Then run the wired command above and confirm the
caller's voice registers with `scripts/bt_audio_diagnostic.py --capture --input "<your line-in>"`.

**Honest caveats for wired:** it is analog line audio (levels, mic-bias and impedance can need a cheap inline
attenuator or a sound card that supplies mic bias); it needs the adapters above; and it is fiddlier to set up than
Bluetooth. It is the right choice **only** because you asked to avoid Bluetooth. Bluetooth HFP needs **zero
hardware** and already worked on your PC — it is the faster way to a working call if you can accept Bluetooth.

Either way, the two-way audio must be confirmed on a real consented call in **Devices → Audio feasibility console**
before the release gate opens; the bridge never fabricates a pass.

## 5. Release gate (unchanged, and this is the point)

Autonomous calling stays disabled until **both** directions are proven on a **real device**: the remote party's
voice captured through a verified digital/line input, and Priya's voice delivered into the **same** live call —
never an acoustic speaker-to-mic relay. The evidence is confirmed by the operator in **Devices → Audio
feasibility console**; only then does `release_gate.autonomous_calling_allowed` open, and promotional campaigns
additionally require Indian DLT/TRAI compliance (`docs/COMPLIANCE_INDIA.md`). The USB ADB diagnostic above
produces control-plane evidence (dial/state/hangup); it explicitly does **not** open the audio gate.

## 6. Exotel is now optional

Exotel code remains in the repo as an **optional** provider (`provider.enabled` defaults to **false**, credentials
are env-only, and the backend runs with no Exotel environment at all). It is no longer presented as the production
path. If you never set it up, nothing changes and no cloud service is contacted. Use it only if you later decide a
cloud ExoPhone caller-ID is acceptable (it is **not** your Jio number — `docs/EXOTEL_EVALUATION.md`).
