# Jio USB-modem voice feasibility — verify before you buy

Status date: 2026-10-18.

**Bottom line: do NOT buy a modem yet.** It is not established that any specific USB cellular modem makes
**VoLTE voice calls on Jio in India with two-way USB call audio**. A modem that does LTE *data* on Jio can still
be useless for *voice*. This page says exactly what to confirm, and on which modem, before spending anything. If
those checks cannot be passed, the honest conclusion is that the Jio-over-USB-modem route is **not proven** and no
purchase should be recommended.

## Why Jio makes this harder than usual

Jio runs a **VoLTE-only** network in India: there is no 2G/3G circuit-switched voice to fall back to. So a modem
cannot place a Jio voice call the "old" CS way — it **must register IMS and do VoLTE**. Many USB modems:

- are **data-only** (no voice firmware, no USB audio function at all); or
- support CS voice on other carriers but **do not register VoLTE/IMS on Jio**; or
- expose voice only over a path the Asterisk driver can't use (the `chan_modemmanager` driver needs **USB
  audio-class** audio, not AT/tty audio).

So three independent things must all be true on the **exact** modem + firmware + Jio SIM:
1. the modem registers **VoLTE/IMS on Jio** (voice, not just data);
2. its **call audio is on a USB audio-class device** (reachable by ModemManager/ALSA/Asterisk);
3. real **two-way** audio actually flows on a live Jio call.

## What the evidence says so far

- `asterisk-chan-modemmanager` is tested on **Quectel RM500Q / EM05 / EC25** — but on **Korea LGU+**, including
  VoLTE. No India/Jio result is claimed.
- Quectel forums show the EC25 family *can* do VoLTE, but only with the **right firmware + the carrier's MBN
  profile loaded and IMS enabled**; users repeatedly hit "IMS not registering" with stale/wrong carrier profiles.
  Voice-over-USB needs `AT+QPCMV` and some firmware fixes the USB-audio (UAC) rate at 8 kHz (fine for telephony,
  no HD voice). Nothing there confirms **Jio** specifically.
- No source we found confirms a named modem doing **VoLTE voice on Jio over USB audio**. Treat it as **unproven**
  until you verify it on hardware.

(Sources are listed at the end.)

## Pre-purchase verification checklist

Do these **in order**. Stop at the first hard failure — that failure is the answer, and it saves the purchase.

**A. Paper check (before buying) — the modem's own spec sheet must say, in writing:**
- [ ] **Voice function** supported (not "data only").
- [ ] **VoLTE / IMS** supported on the firmware variant sold to you.
- [ ] **Voice over USB (UAC / PCM-over-USB)** supported — this is what Asterisk needs. (For Quectel, the
      "Voice Over USB and UAC Application Note" and `AT+QPCMV`.)
- [ ] LTE **bands for India / Jio**: B3 (1800), B5 (850), B40 (2300), B1 (2100); ideally B28 (700, Jio's
      low-band) — many global modems **omit B28**.
- [ ] A firmware + **carrier MBN profile** that includes a Jio/India IMS profile (ask the vendor explicitly).

If the vendor cannot confirm VoLTE **and** voice-over-USB **and** India bands, **do not buy that modem.**

**B. Borrow/return-window check (a real Jio SIM in the modem) — safe diagnostic AT/`mmcli` steps:**
- [ ] Modem registers on Jio for **data** (`mmcli -m 0`, state `registered`).
- [ ] IMS/VoLTE is **enabled and registered** (check the modem's IMS query; e.g. Quectel `AT+QCFG="ims"` and the
      modem's IMS registration status). If IMS never registers on Jio, **stop — this modem won't do Jio voice.**
- [ ] A Jio **carrier profile** is available/active (e.g. Quectel `AT+QMBNCFG="list"`).
- [ ] **Voice over USB** turns on (e.g. `AT+QPCMV=1,2`) and a **USB audio device appears** on the host
      (`arecord -l` / `aplay -l` show the modem card). No USB audio device = `chan_modemmanager` cannot bridge it.

**C. Live two-way test on Jio (consenting participant, designated test number):**
- [ ] Place a call to a consenting number; it **connects** on Jio VoLTE.
- [ ] The remote party's voice is captured **digitally off the modem** (recorded on the host), intelligible.
- [ ] Generated speech is **heard clearly by the remote party**.
- [ ] Both directions work **in the same call**, with acceptable latency; record the evidence.
- [ ] Repeat for an **inbound** call to the Jio number.

Only when A, B and C all pass on the exact modem+firmware+SIM is the Jio-over-USB-modem route **proven**. Record
each result (expected, actual, device/firmware, evidence, pass/fail/blocked) and confirm it in SELL AGENT's
audio-feasibility console — the same evidence gate that governs the autonomous loop.

## Candidate modems to ask the vendor about (not endorsements)

Ask specifically for VoLTE + Voice-over-USB + India bands + a Jio-capable carrier profile. Do **not** assume a
model works from its name alone — Quectel voice/VoLTE/UAC support varies by **variant and firmware**:

- Quectel **EC25-E / EC25-EU** (LTE Cat-4; EU/India bands incl. B28 on EC25-E) — voice + UAC on the right
  firmware; the most commonly reported India option, **but Jio VoLTE still must be verified**.
- Quectel **EG25-G** — global bands, VoLTE-capable with the correct MBN; same verification applies.
- Quectel **RM500Q-GL** (5G) — tested by the Asterisk driver (on LGU+), higher cost/power; India/Jio unverified.

## Cost and compliance (so there are no surprises)

- **One-time:** modem (~₹5,000–12,000 typical), a USB hub/power, optional dedicated mini-PC. Software is free and
  local (Asterisk, ModemManager, SELL AGENT's local AI). **No paid API, no SIP subscription** — this route uses
  your existing Jio SIM in the modem.
- **Jio number:** this route keeps the **Jio SIM as the calling identity** only if the SIM sits in the modem.
  That means the number moves off the S25 for gateway calls (or you use a second Jio SIM). This is real cellular
  voice on the Jio number — not a SIP DID pretending to be it.
- **Compliance (India):** promotional/telemarketing calls are regulated under **TCCCPR-2018 / TRAI**. Bulk or
  unregistered promotional calling from an ordinary number risks disconnection and blacklisting. Outbound
  promotional autonomous calling stays **disabled** until the applicable DLT/consent requirements are met; see
  `docs/COMPLIANCE_INDIA.md`. Human-assisted, consented calls are unaffected.

## If Jio compatibility cannot be established

Then say so plainly and **do not recommend a purchase**. The fallback remains what ships today: **human-assisted
mode on the existing Galaxy S25** (SELL AGENT suggests lines, keeps transcript + CRM; the operator speaks). A
licensed SIP/PSTN trunk is a separate option but it would **not** use the Jio number as caller ID and needs your
approval for a paid subscription, so it is out of scope unless you ask for it.

## Sources

- Android, "Sharing audio input" (who may capture call audio): https://developer.android.com/media/platform/sharing-audio-input
- Quectel forums — EC25 VoLTE / IMS enablement and Jio: https://forums.quectel.com/t/ec25-e-enabling-volte/33327 , https://forums.quectel.com/t/volte-capability-ec25-e/10243
- Quectel forums — Voice over USB / UAC: https://forums.quectel.com/t/ec25-voice-over-usb/4262 , "EC2x&EG9x Voice Over USB and UAC Application Note"
- Quectel forums — EG25-GC VoLTE/IMS not registering (stale MBN): https://forums.quectel.com/t/eg25-gc-volte-ims-not-registering-request-latest-firmware-and-updated-cu-mbn/59337
- `asterisk-chan-modemmanager` tested modems/carrier (LGU+ Korea): https://github.com/koreapyj/asterisk-chan-modemmanager
