# Exotel AgentStream — provider evaluation (production calling route)

Status date: 2026-10-19. Evaluated from Exotel's public AgentStream documentation and product pages. The Exotel
developer host was not reachable from the build environment, so **field names and prices below must be confirmed
against your own Exotel account before production** — they are marked accordingly.

## 1. What it is and why it fits

Exotel AgentStream places the **real cellular call** over Exotel's carrier infrastructure and streams **both sides
of the live audio** to your application over a **bidirectional WebSocket** (the "Voicebot/Stream" applet). Your
app runs the AI and streams audio back, which Exotel plays to the caller in real time. This removes the Galaxy
S25/Jio call-audio problem entirely: Exotel owns the telephony leg; SELL AGENT keeps **all AI local** and only
exchanges telephony audio.

| Property | Value (confirm on your account) |
|---|---|
| Audio format | raw **linear16 PCM**, 16-bit signed, mono; also mulaw in some applets |
| Sample rate | **8000 Hz default**; 16000 / 24000 selectable via a `sample-rate` query param on the StreamUrl |
| Transport | base64 PCM inside JSON `media` events over WSS; chunks a **multiple of 320 bytes**; max session **60 min** |
| Direction | caller→AI as inbound `media`; AI→caller by sending `media` events back; `clear` flushes queued audio (barge-in) |

This is the **same shape** as the AudioSocket path already in this repo, so SELL AGENT's local loop
(faster-whisper → conversation engine with approved FITRON facts + guardrails + female Piper voice → TTS, VAD,
barge-in, opt-out) runs over it unchanged.

Sources: Exotel AgentStream WebSocket protocol & "Connect Voice AI" developer docs, the AgentStream product page,
and the Exotel support "Stream and Voicebot applet" guide (developer.exotel.com / docs.exotel.com / exotel.com).

## 2. Account enablement & registration (required before any call)

- A **business Exotel account** with KYC (company documents). Not a personal signup.
- One or more **ExoPhone** virtual numbers — this is the **caller ID** for outbound calls.
- **AgentStream / Voicebot streaming** enabled on the account (may be beta/allowlisted — request from Exotel).
- API credentials: **API Key, API Token, Account SID, subscriber subdomain** (`api.exotel.com` or `api.in.exotel.com`).
- **DLT / TRAI registration** for promotional/transactional calling (see §5). Exotel will not run promotional
  campaigns without this.

## 3. Caller ID — do NOT assume the Jio number

**The outbound caller ID is the Exotel ExoPhone, not your Jio number.** Showing your existing Jio 10-digit mobile
number as the caller ID on provider-originated calls is **not** available by default and may not be permitted for
promotional traffic at all. If you need your Jio number as the caller ID, you must get **written confirmation from
Exotel** that your specific campaign supports it; otherwise plan for the ExoPhone to be the number recipients see.
The app enforces this: `provider.caller_id` is the ExoPhone and the adapter sends it as `From`/`CallerId`.

## 4. Pricing (verify at exotel.com/pricing — do not treat as a quote)

Exotel pricing is account- and volume-specific. Typical components to budget for (confirm current rates):
- **Platform / subscription** fee (monthly).
- **ExoPhone rental** (per number per month).
- **Per-minute outbound call charges** (billed per call leg; varies by destination and plan).
- **AgentStream / streaming** usage, if billed separately.
- Possible **setup / KYC** and minimum commitments.

There is no free tier for production promotional calling. **This is a paid service** — SELL AGENT will not create
an account, pay, or commit on your behalf. The **AI remains free and local**; only the telephony is paid.

## 5. Indian telecom compliance (gating, not optional)

Promotional voice calls in India are regulated (TRAI TCCCPR). Before any production campaign:
- Register as a sender/telemarketer on the **DLT** platform as applicable; use the correct **numbering series**
  for the call type; honour **DND / consumer preferences**; keep **consent** records; implement **opt-out**.
- Get **Exotel's written confirmation** that your caller ID and campaign type are permitted.
See `docs/COMPLIANCE_INDIA.md`. SELL AGENT keeps **promotional autonomous campaigns disabled** until these are in
place, and the per-contact eligibility checks (consent, suppression, quiet hours, limits) run on every call.

## 6. Reachability: the AI is local, Exotel is cloud — you need a secure relay

Exotel (cloud) must reach your **StreamUrl**, but the AI runs on your **local Windows PC**. Options:
- An **authenticated tunnel** (e.g. Cloudflare Tunnel / `cloudflared`, or ngrok) that exposes only the
  `/api/v1/exotel/stream` WebSocket, protected by the `EXOTEL_STREAM_TOKEN`. Cost: free tier exists for
  cloudflared; ngrok has paid tiers for stable URLs.
- A small **cloud relay VM** that forwards the WebSocket to your PC over an authenticated channel.
Security: the endpoint is **token-authenticated and fails closed** (no token → refused). **Never** expose it
without the token. The AI inference never leaves your PC regardless of the relay.

## 7. What is implemented in this repo (milestone 1)

- `telecom/exotel.py` — `ExotelProvider` (route `exotel`): dials via the Exotel Connect API (`From`/`To`/`CallerId`
  = ExoPhone, `StreamUrl` tagged with our call id), fail-closed `call_audio_path`, and `ExotelStreamTransport`
  (bidirectional, re-chunks to exact frames, bounded, barge-in `clear`).
- `api/v1/exotel_ws.py` — the token-authenticated `/api/v1/exotel/stream` WebSocket that Exotel connects to;
  decodes inbound `media`, plays AI audio back as `media`, flushes on barge-in, binds/unbinds per call.
- Settings `provider.*`, eligibility + release-gate handling for the `exotel` route, and the `exotel` capability
  in `/call-jobs/routes`.
- Tests (`tests/integration/test_exotel.py`): media encode/decode + re-chunking, caller-ID = ExoPhone,
  disabled-route refusal, fail-closed audio path, and the WebSocket bind + inbound-audio bridge. **Simulated** —
  no Exotel account, no real call.

## 8. What still needs YOU (not fakeable here)

1. An Exotel business account, ExoPhone, AgentStream enablement, and API credentials.
2. DLT/TRAI registration and Exotel's caller-ID/campaign confirmation.
3. A secure tunnel for the StreamUrl.
4. A **real consented test call** to verify two-way audio, then confirm it in the audio-feasibility console to
   open the release gate.
Until those exist, the Exotel route is built and tested in simulation but **cannot place a real call**, and
autonomous calling stays disabled. See `docs/PRODUCTION_READINESS.md`.

## 9. Open-source alternative (no provider fees)

The same local loop also runs over **Asterisk + AudioSocket** (`docs/CALLING_ARCHITECTURE.md`,
`telecom/audiosocket.py`) — self-hosted, no per-minute provider fees, but you operate Asterisk and supply the
telephony (a SIP trunk or the USB-modem route, `docs/JIO_MODEM_FEASIBILITY.md`). Exotel is the lower-ops, paid
option; Asterisk is the free, higher-ops option. Both are supported behind the same gate.
