# Bluetooth two-way audio (SIMVox-AI path) — investigation & diagnostic

Status date: 2026-10-19. Device: Samsung Galaxy S25 (SM-S931B), Jio. PC: Windows 11, 16 GB RAM, no dedicated GPU.

**Target asked for:** Jio call ↔ Galaxy S25 ↔ **Bluetooth HFP** ↔ Windows audio ↔ local STT → local LLM → local
female TTS ↔ back into the call.

**Honest finding up front:** the all-wireless Bluetooth leg hinges on the **PC acting as the phone's Bluetooth
hands-free unit** (a car-kit/headset the phone sends its call audio to). On many Windows PCs that device does not
exist — but **it must be checked per machine, because some do expose it**.

> **Verified on a real device (2026-10-19).** On the operator's own Windows 11 PC + Galaxy S25 (shown as "Galaxy
> S26" in the pairing) on Jio, after pairing and routing the live call to the PC, Windows exposed a
> **"Hands-Free HF Audio"** input **and** output. On a real consented call both directions worked: the caller's
> voice was captured on the PC (operator confirmed hearing it in `caller_test.wav`), and a tone played from the
> PC was heard by the remote party. This clears the two-way-audio blocker **on that machine**. It does not
> generalise — each PC/stack is different — and it is not yet a full autonomous-call pass (Hindi/English quality,
> latency, interruptions and Jio Wi-Fi Calling on a real call still need checking), so the release gate stays
> closed until those are confirmed.

SELL AGENT's local AI is ready to run over this path (the runner below); the release gate stays closed until the
real-device conversation tests pass.

## 1. What SIMVox-AI actually is (code-level)

Repo: `Magraa/SIMVox-AI` (MIT). Inspected 2026-10-19.

| Part | What it does | Reality |
|---|---|---|
| `phone_controller.py` | Drives the phone over **ADB** (USB or wireless): `telecom accept-call`, `telecom end-call`, `am start … tel:`, `input keyevent`, `dumpsys` for call state. | Sound, no root. SELL AGENT's companion already does the equivalent. |
| `audio_router.py` | Captures/plays audio with **`sounddevice`** on a named Windows input/output device, with simple VAD. | **It implements no Bluetooth stack.** It just reads/writes whatever OS audio device you name. |
| `ai_engine.py` | **Google Gemini** (cloud LLM) + **Edge-TTS** (cloud voices) + `SpeechRecognition` (defaults to Google cloud STT). A local **Kokoro** TTS loader exists but is optional. | Cloud-dependent by default — not acceptable for us (see §3). |
| `database.py` | SQLite CRM/transcripts. | Fine; SELL AGENT already has its own. |
| bundled `scrcpy-win64` | ADB + screen mirror binaries. | Convenience only. |

**Key point:** SIMVox's "Bluetooth HFP support" is entirely *"name the Windows device that is your phone's
hands-free channel."* It assumes the OS already exposes the live call as a recording device **and** a playback
device. Everything rides on that assumption.

## 2. Can Windows 11 be the phone's Bluetooth hands-free endpoint?

Bluetooth calls use the **Hands-Free Profile (HFP)** with two roles: the **Audio Gateway (AG)** = the phone, and
the **Hands-Free unit (HF)** = the car-kit/headset that receives the call audio and feeds its mic back. For the PC
to capture the S25's call, the **PC must be the HF unit**.

- Desktop Windows implements the HFP **AG** role (so a Bluetooth *headset* can serve the PC's own Teams/Zoom
  calls). The device Windows shows as **"Hands-Free AG Audio"** is the PC-as-gateway direction — **not** the PC
  receiving a phone's call. ([elevenforum](https://www.elevenforum.com/t/bluetooth-hands-free-ag-audio.5768/), [Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/3917463/how-do-i-disable-hands-free-ag-audio))
- Microsoft's **HF-unit** role is documented only for **Windows Embedded / NavReady** devices, not desktop
  Windows. ([MS: Hands-Free Unit role](https://learn.microsoft.com/en-us/previous-versions/windows/embedded/cc510823(v=msdn.10)))
- Desktop Windows historically supports A2DP **source** only; the **sink** role (music) needs a third-party app
  ("Bluetooth Audio Receiver") and even that is **A2DP music, not HFP call audio**. ([Intel A2DP](https://intel.com/content/www/us/en/support/articles/000030412.html), [Winaero](https://winaero.com/enable-and-use-a2dp-sink-for-bluetooth-in-windows-10))

**Conclusion:** on a stock Windows 11 PC there is normally **no device that carries the S25's live cellular call
audio over Bluetooth**, because Windows won't be the phone's hands-free unit. The diagnostic confirms this on your
machine rather than trusting this write-up.

### Paths that can actually carry the audio (if you want two-way without root)

1. **A real Bluetooth HFP hardware adapter** (a car-kit / BT-to-3.5mm or BT-to-USB receiver that genuinely pairs
   to the S25 as a headset), whose line-out/line-in is fed into the PC via a **USB audio capture dongle**. The
   Bluetooth leg is phone↔adapter; the PC sees a normal USB audio device. Costs a small adapter; adds one
   analog hop. **This is what most SIMVox users actually rig up.**
2. **USB cellular modem + Asterisk** (already built — `docs/CALLING_ARCHITECTURE.md`): cleaner digital audio, no
   acoustic hop, but needs a modem verified on Jio VoLTE (`docs/JIO_MODEM_FEASIBILITY.md`).
3. The S25 is not rooted and nothing here roots it; Android's own call-audio APIs stay closed to apps
   (`docs/S25_COMPATIBILITY.md`).

The **3.5mm TRRS splitter** option in SIMVox does not apply: the Galaxy S25 has no headphone jack.

## 3. Local AI instead of Gemini / Edge-TTS (no cloud, no paid keys)

The conversation brain is **not** SIMVox's — it is SELL AGENT's existing local stack, which already replaces every
cloud dependency SIMVox ships:

| SIMVox default (cloud) | SELL AGENT local replacement | Where |
|---|---|---|
| Google Gemini LLM | local LLM (llama.cpp / Ollama-class GGUF) via the conversation engine, script-mode fallback | `services/ai-engine` |
| Edge-TTS neural voices | **Piper** female Hindi/English (`hi_IN-priyamvada-medium`, `en_US-*`) | `services/speech-engine/tts.py` |
| `SpeechRecognition` (Google STT) | **faster-whisper** local | `services/speech-engine` |
| its SQLite | SELL AGENT SQLite CRM | `services/local-backend` |

So nothing cloud is mandatory. The Bluetooth/local-audio bridge only needs to deliver PCM frames; the rest of the
loop (VAD, barge-in, opt-out, approved FITRON facts, female "Priya" persona, CRM) is the code already shipped and
tested. Benchmarks of latency/memory on the 16 GB CPU-only PC are to be recorded with `tests/voice` and the
persona preview once models are installed (not yet measured here — the sandbox cannot download models).

## 4. How the bridge plugs into SELL AGENT

The PC-side bridge reuses the existing **media-gateway** seam — no new call pipeline:

```
 S25 cellular call ──(Bluetooth HFP hardware / USB audio)──► Windows input device  ┐
                                                                                    │  LocalAudioTransport
 S25 call uplink  ◄─(Bluetooth HFP hardware / USB audio)──── Windows output device ┘  (telecom/local_audio.py)
                                                                                    │
                                        MediaGatewayAdapter.bind(call_id, transport) │  (release-gate-fenced)
                                                                                    ▼
          existing local loop: VAD → faster-whisper → conversation engine (approved facts, guardrails,
                      consent/opt-out) → female Piper TTS → back into the call; barge-in, cancel, handoff
```

- `telecom/local_audio.py` — `LocalAudioTransport` (sounddevice, lazy-imported, PC-only) + the pure, unit-tested
  helpers `classify_devices` / `capture_evidence`.
- Phone control (dial/answer/hang-up/state) stays with SELL AGENT's companion / ADB, as SIMVox does.
- Fail-closed: a path is handed to the loop only when the release gate is open **and** a real device is bound.
  Capturing signal on a device is never, by itself, treated as success.

## 5. Diagnostic (run on the real PC — this is the evidence step)

`scripts/bt_audio_diagnostic.py` (no root, read-only):

```
python scripts/bt_audio_diagnostic.py --list                       # audio devices; flags phone/HFP channels
python scripts/bt_audio_diagnostic.py --adb                        # ADB reachable? current call state
# place a consented test call on the S25, route its audio to the paired PC/adapter, then:
python scripts/bt_audio_diagnostic.py --capture --input "Hands-Free" --seconds 6 --out bt_evidence.json
```

It writes honest numbers (RMS, peak, distinct samples) and a `has_signal` flag, and **prints a warning when no
two-way phone/HFP device exists**. `has_signal` means *some* audio was on the device — it is **not** proof it was
the remote party. You confirm that against the live call, then record it in the audio-feasibility console.

## 5b. Run Priya over Bluetooth (after the diagnostic shows a two-way device)

`scripts/run_priya_bluetooth.py` runs the whole local loop over the Hands-Free devices. **Supervised, one
consenting participant — not a bulk dialer.** It discloses it is an AI, speaks only approved FITRON facts, honours
opt-out, and Ctrl-C is an emergency stop.

First, prove the setup with no phone or models needed:
```
python scripts/run_priya_bluetooth.py --selftest       # checks Priya's brain: disclosure, ₹1,999-only, Hindi switch, opt-out
```
Install the local models once (sizes/licences printed first):
```
python scripts/download_models.py --whisper small --piper hi_IN-priyamvada-medium en_US-lessac-medium --yes
```
Then, on a **live consented call** with audio routed to the PC:
```
python scripts/run_priya_bluetooth.py --list-devices                      # confirm the HF Audio devices
python scripts/run_priya_bluetooth.py --consent --contact "Rahul" --business "Power Gym"
```
Windows one-click equivalents: `scripts\run_priya_bluetooth.bat selftest` / `devices` / `call "Rahul" "Power Gym"`.
The transcript and outcome are saved locally under `priya_calls/`. Autonomous dialing of lists stays out of scope
(`docs/COMPLIANCE_INDIA.md`).

## 6. Acceptance tests (label each honestly; none auto-passes)

Run on the S25 with a consenting participant and a designated test number. Record expected/actual/evidence and
mark **simulated / automated / real-device-tested**:

1. ADB connects to the S25. 2. A test call initiates via supported controls. 3. Remote speech genuinely captured
by Windows. 4. AI speech genuinely heard by the remote participant. 5. Both directions in the **same** call.
6. Hindi. 7. English. 8. Language switching. 9. Latency. 10. Barge-in / cancellation. 11. Network interruption.
12. Emergency stop. 13. **Jio Wi-Fi Calling (VoWiFi)** specifically — do **not** assume it behaves like a normal
cellular call; test it on its own. 14. Screen-locked. 15. End-to-end FITRON conversation.

Steps 3–5, 8–12, 15 map to the backend diagnostic plan; the gate opens only on operator-confirmed **real-device**
evidence for both directions.

## 7. Known limitations (today)

- Windows almost certainly **cannot** be the S25's Bluetooth hands-free unit, so the fully wireless path likely
  needs a small **BT-HFP hardware adapter + USB audio dongle**, which adds one analog hop (quality/echo to
  measure). The diagnostic will tell you what your PC actually exposes.
- **Wi-Fi Calling (VoWiFi)** may route or gate audio differently from cellular VoLTE; it is a separate test.
- No real two-way Jio call has been demonstrated here. Nothing in this change claims the S25/Jio Bluetooth path
  works; autonomous calling stays disabled until the real-device tests pass.
- Latency/memory of the local models on the 16 GB CPU-only PC are **not yet measured** (models can't be
  downloaded in the build sandbox); record them with `tests/voice` and the persona preview.
