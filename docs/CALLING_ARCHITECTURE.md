# Calling architecture: how SELL AGENT gets real two-way AI call audio

Status date: 2026-10-18.

The conversation loop is the same everywhere (caller speech → local faster-whisper STT → conversation engine with
approved FITRON facts + guardrails → local female Piper TTS → back into the call), with language switching,
barge-in, cancellation, opt-out and human handoff. What changes between options is **only the audio transport** —
how the remote party's voice reaches SELL AGENT and how the AI's voice reaches the call. That transport is a
single, documented seam: the **media gateway** (`sellagent_backend/telecom/media_gateway.py`). Business logic
never talks to telephony directly.

## The three options

| | A. Galaxy S25 + Jio companion | B. Dedicated USB cellular modem + Asterisk | C. Licensed SIP/PSTN trunk |
|---|---|---|---|
| Place / receive real calls | Yes | Yes (modem, via Asterisk) | Yes |
| Two-way **digital** audio to the AI | **No** (Android blocks it) | **Yes, if the modem does Jio VoLTE voice over USB** | Yes |
| Needs root / system privilege | Would (impossible on S25) | **No** (modem's own USB voice) | No |
| Wi-Fi Calling (VoWiFi) | Phone handles it | Modem VoLTE/VoWiFi dependent | N/A (IP trunk) |
| Keeps the existing **Jio number** | Yes | **Yes, SIM in the modem** | **No** (trunk DID, not your Jio number) |
| One-time / recurring cost | None | Modem (~₹5–12k), no subscription | Trunk + **paid per-minute/subscription** |
| Status | **Ships today** (human-assisted) | **Candidate — Jio voice unverified** | Not pursued (paid; needs approval; loses Jio number) |

- **A is the default and only autonomous-capable option on the *existing phone*** — and on the S25 autonomous is
  blocked (`docs/S25_COMPATIBILITY.md`), so A stays **human-assisted**: SELL AGENT suggests the next line, keeps
  the transcript and CRM, the operator speaks.
- **B is the recommended path for autonomous calling that keeps the Jio number**, using open-source software and
  local AI with no paid services. It replaces the *phone* with a voice-capable USB modem — it does **not** modify
  or root the S25. Its one hard dependency is that the modem actually does **VoLTE voice on Jio with USB audio**,
  which must be **verified before purchase** (`docs/JIO_MODEM_FEASIBILITY.md`).
- **C** (a SIP/PSTN trunk) gives reliable two-way audio but uses a trunk number, not your Jio SIM, and needs a
  paid subscription — so it is out of scope unless you explicitly ask. A SIP trunk does **not** automatically use
  your Jio number; caller ID would be the trunk's.

## Option B in detail (the recommended autonomous path)

```
  Jio SIM in a VoLTE voice-capable USB modem
        │  (cellular VoLTE/IMS voice; USB audio-class PCM)
        ▼
  ModemManager  ──►  Asterisk  +  chan_modemmanager   (GPL-2.0, separate process)
        │                 │
        │   AudioSocket(<call-uuid>, 127.0.0.1:9092)   ← 8 kHz slin, 320-byte/20 ms frames
        ▼                 ▼
  SELL AGENT backend: AudioSocket server ──► media-gateway route ──► CallAudioPath
        │
        ▼
  existing local AI loop: VAD → faster-whisper STT → conversation engine (approved FITRON facts, guardrails,
        consent/opt-out) → female Piper TTS (Hindi/English) → back into the call; barge-in, cancel, handoff
```

Why this is safe and in-policy:
- **No Android bypass, no root.** The modem exposes its own voice as USB audio; Asterisk reads it with stock
  packages. The S25 is untouched.
- **Separation of concerns.** Asterisk/ModemManager run as separate processes and reach SELL AGENT only over a
  **loopback** AudioSocket connection. GPL stays on their side of the socket; our backend is not linked to it.
- **Local and free.** STT (faster-whisper), the conversation engine, and TTS (Piper) are the project's existing
  local components. No paid API, no SIP subscription — the call rides your Jio SIM in the modem.
- **Fail-closed.** The media-gateway route hands the loop a verified audio path **only** when the release gate is
  satisfied by real-device evidence, the gateway is enabled, and a live gateway is bound to the call. Otherwise
  autonomous start is refused and the operator keeps the call.

### What is already implemented in this repo

- **`telecom/media_gateway.py`** — the modular audio gateway: a documented `MediaTransport` interface, the
  `SipRtpCallAudioPath` (PCM↔float32, bounded jitter buffer with drop-oldest backpressure, health timeout,
  real-time pacing, clean close), and the `MediaGatewayAdapter` (route `media_gateway`, fail-closed
  `call_audio_path`, dial/cancel delegation, UUID→call resolution).
- **`telecom/audiosocket.py`** — the Asterisk **AudioSocket** server + transport (8 kHz slin, the standard
  UUID/AUDIO/HANGUP framing), loopback-only, one connection per call, refusing unknown call UUIDs. Started on boot
  when `gateway.enabled`.
- **Settings** (`gateway.*`): `enabled`, `kind` (`sip`/`gateway_phone`), `bind_host` (loopback-enforced),
  `sip_host`/`sip_port`, `audiosocket_port`, `codec`, `caller_id`.
- **Eligibility + release gate**: the `media_gateway` route is blocked unless the gateway is configured, and
  autonomous use still requires the real-device two-way-audio evidence gate.
- **Tests**: `tests/integration/test_media_gateway.py` and `test_audiosocket.py` cover the PCM path, backpressure,
  fail-closed gating, the AudioSocket wire protocol, UUID binding, and a full autonomous conversation over the
  route (barge-in + Hindi/English switching), all with simulated audio.

### What is NOT done (and must not be claimed as done)

- No modem has been verified on **Jio VoLTE voice over USB** — the whole of Option B depends on this
  (`docs/JIO_MODEM_FEASIBILITY.md`). Nothing here proves a real Jio call carried AI audio.
- The Asterisk dialplan/`chan_modemmanager` config, outbound dial control from the backend, and the on-device
  15-step live-audio diagnostic on real hardware remain to be run by the operator on the target machine.
- The release gate stays **closed** until operator-confirmed real-device evidence exists for both directions.

### Operator setup outline (once a Jio-capable modem is verified)

1. Verify the modem on Jio per `docs/JIO_MODEM_FEASIBILITY.md` (do not skip — this is the go/no-go).
2. Install Asterisk + ModemManager + `asterisk-chan-modemmanager` (stock packages); add the modem; enable USB
   voice.
3. Dialplan: answer/originate on the modem channel and `AudioSocket(${CALLUUID},127.0.0.1:9092)`, passing the
   SELL AGENT call id as the UUID.
4. In SELL AGENT: set `gateway.enabled=true`, `gateway.kind=gateway_phone`, keep `bind_host` on loopback.
5. Run the 15-step live-audio diagnostic with a consenting test participant; confirm both directions in the
   audio-feasibility console. Only then does the gate open and autonomous calling become available.
