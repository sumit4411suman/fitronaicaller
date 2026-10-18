# Telephony bridge evaluation

Four open-source projects were evaluated as ways to give SELL AGENT real two-way call audio. For each: what it
actually does, how it gets call audio, what hardware/privileges it needs, whether it fits the Galaxy S25 / Jio,
its licence, and whether we reused any of it. None of their source was copied; where we adopted an idea it is a
public protocol or a design pattern, re-implemented.

Evaluated 2026-10-18 from the public repositories at that date.

## Summary

| Project | Licence | Audio mechanism | Needs root? | Hardware proven | S25? | Jio? | Verdict for us |
|---|---|---|---|---|---|---|---|
| sidinsearch/AgentCall | AGPL-3.0-only | Privileged system app captures downlink, injects via Qualcomm `incall_music`; PC over USB | **Yes** (Magisk, priv-app) | Xiaomi POCO M2 Pro only | No | Not tested | Reference only; incompatible device/root model |
| OriginStackHQ/GSM2SIP | **No LICENSE file** | Same Qualcomm digital path, bridged to SIP; Magisk module | **Yes** (Magisk) | Redmi Note 7 Pro, Poco X3 NFC | No | Not tested; Exynos = no path | Idea reused (GSM↔SIP gateway), not code; unlicensed |
| koreapyj/asterisk-chan-modemmanager | GPL-2.0-only | USB cellular **modem** voice via ModemManager + ALSA USB audio into Asterisk | **No** (needs a voice modem) | Quectel RM500Q/EM05/EC25, Korea LGU+ | n/a (not the phone) | **Unverified** | Recommended path's cellular leg; see Jio report |
| ictinnovations/asterisk-ai-voice-agent | MIT | Asterisk **AudioSocket** (8 kHz slin TCP) → STT→LLM→TTS sidecar | No | Self-hosted | n/a | n/a | Protocol + pattern reused; we implemented our own local sidecar |

## 1. sidinsearch/AgentCall (AGPL-3.0-only)

- **What:** turns a rooted Android phone into a cellular voice endpoint for a PC AI over one USB cable. Default
  dialer app + a desktop gateway; real SIM calls, STT/TTS, recordings, MCP control.
- **Audio mechanism:** a **privileged system app** (installed via a Magisk module into a protected system
  partition) holding `CAPTURE_AUDIO_OUTPUT` + `MODIFY_PHONE_STATE` captures the downlink and injects the uplink
  through a Qualcomm `incall_music` mixer path; audio reaches the PC over USB/ADB, loopback-only.
- **Requirements:** Magisk root, platform-signed privileged permissions, and a Qualcomm audio HAL. The only
  **qualified** device is the Xiaomi POCO M2 Pro (`gram`/`atoll`), Android 15, for a single bounded call; the
  docs explicitly say support does not extend to other ROMs/phones and that **Samsung Exynos is not usable**.
- **S25/Jio:** no. The S25 cannot be rooted (`docs/S25_COMPATIBILITY.md`) and is not a qualified device.
- **Licence:** AGPL-3.0-only (the NOTICE also flags unresolved upstream provenance from an earlier gsm2sip
  import). AGPL would force us to publish our own backend under AGPL if we linked its code. **We did not copy any
  AgentCall code.**

## 2. OriginStackHQ/GSM2SIP (no licence)

- **What:** a dedicated rooted Qualcomm phone acts as a GSM↔SIP gateway: inbound SIM calls are answered and
  bridged to a SIP server; the server can place outbound calls through the SIM.
- **Audio mechanism:** the same Qualcomm digital path as AgentCall (modem downlink capture; uplink injection via
  `incall_music`), with the handset mic/speaker muted, bridged to SIP (G.722/G.711, SRTP). A Magisk module
  relaxes Android's audio-concurrency limits and keeps the app's root grant.
- **Requirements:** Magisk root on a Qualcomm device whose vendor image exposes the `incall_music` mixer.
  Verified on Redmi Note 7 Pro and Poco X3 NFC. **Galaxy S10e (Exynos) is listed as "no path in either
  direction."**
- **S25/Jio:** no (Exynos/root). Already evaluated previously in this project.
- **Licence:** **no LICENSE file** → default "all rights reserved." We must **not** copy its code. We reuse only
  the *architectural idea* of a GSM↔SIP gateway feeding a local SIP server, re-implemented from Asterisk's public
  interfaces.

## 3. koreapyj/asterisk-chan-modemmanager (GPL-2.0-only)

- **What:** an Asterisk channel driver that turns a **USB cellular modem** (managed by ModemManager) into a phone
  line — voice in/out, SMS, MMS — using **stock** Asterisk/ModemManager packages, no rebuilds.
- **Audio mechanism:** the modem's **USB audio-class** sound card carries the call PCM; the driver auto-detects
  the ALSA device and bridges it into Asterisk. This is the modem's own voice function, **not** an Android audio
  hack — no root, no phone. (The driver notes "tty audio is not supported": the modem must expose USB audio.)
- **Requirements:** a modem whose **voice** is exposed through ModemManager and reachable as a USB audio device;
  Asterisk + ModemManager + ALSA; the `asterisk` user in the `audio`/`dialout` groups. Some modems need a per-boot
  AT command to enable USB voice. Tested modems: Quectel RM500Q, EM05, EC25 (UMTS CS and VoLTE/5G).
- **Carrier:** tested on **LGU+ in Korea** including VoLTE. **No India/Jio testing is claimed.**
- **S25/Jio:** not the phone — this replaces the phone with a modem. Whether a given modem does **VoLTE voice on
  Jio** is the open question: see `docs/JIO_MODEM_FEASIBILITY.md`.
- **Licence:** GPL-2.0-only. GPL covers the Asterisk module itself; SELL AGENT does not link it — Asterisk talks
  to us over a network socket (AudioSocket), so there is no GPL linking obligation on our backend. **We did not
  copy its code.**

## 4. ictinnovations/asterisk-ai-voice-agent (MIT)

- **What:** an AI voice sidecar: Asterisk bridges a live call to it over **AudioSocket**, and it runs a
  streaming STT→LLM→TTS loop with barge-in, tool-calling to a CRM webhook, and YAML personas.
- **Audio mechanism:** **AudioSocket** — a documented Asterisk wire protocol: TCP, 8 kHz mono slin, 320-byte
  20 ms frames, a 3-byte header, UUID/AUDIO/HANGUP frame types. Asterisk is the client; the sidecar is the
  server. (It can also use `chan_websocket` on new Asterisk.)
- **Requirements:** Asterisk + the sidecar. Its default STT/LLM (OpenAI/ElevenLabs/Claude) are paid cloud
  services, but the LLM/STT/TTS providers are pluggable (`PORTING.md`), and TTS via **Piper is local and free**.
- **Licence:** MIT — permissive; reuse/adaptation is allowed with attribution.
- **What we reused:** the **AudioSocket wire protocol** (a public Asterisk format, re-implemented in
  `sellagent_backend/telecom/audiosocket.py`) and the **pacing lesson** (meter outbound audio to the 20 ms frame
  clock so a burst of TTS doesn't overrun the far end). We did **not** adopt its sidecar or its paid providers —
  SELL AGENT keeps its own local faster-whisper STT, local female Piper TTS, conversation engine, guardrails and
  CRM. This keeps the stack local and free.

## Licensing bottom line

- We copied **no** source from any of the four.
- AudioSocket is a public Asterisk protocol; re-implementing it carries no licence obligation.
- Asterisk + `chan_modemmanager` (GPL-2.0) run as **separate processes** and talk to SELL AGENT over a socket, so
  their GPL does not reach our backend. If we ever redistribute an Asterisk bundle, its components keep their own
  licences and we ship the corresponding source/notices.
- GSM2SIP has no licence and AgentCall is AGPL — neither's code may be incorporated.
