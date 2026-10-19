# Provider setup — Exotel AgentStream (production calling)

This is the operator checklist to connect SELL AGENT to Exotel so Priya can place real calls. It assumes you have
read `docs/EXOTEL_EVALUATION.md` (costs, compliance, caller-ID caveats). Nothing here is done for you — it needs
your paid Exotel account and your approval.

## 1. Exotel account

1. Create a **business Exotel account** and complete KYC.
2. Buy/assign an **ExoPhone** (this is your caller ID).
3. Ask Exotel to **enable AgentStream / Voicebot streaming** on the account.
4. From the Exotel dashboard, get: **API Key, API Token, Account SID, subscriber subdomain**.
5. Create a **Stream applet / App Bazaar flow** whose Stream/Voicebot step points at your StreamUrl (step 3 below).

## 2. Compliance (do this before any promotional call)

- Complete **DLT / TRAI** registration for your entity and campaign type; use the correct numbering series.
- Get Exotel's **written confirmation** of the caller ID and campaign.
- Keep consent records and opt-out handling (the app enforces consent/suppression/quiet-hours per contact).
- See `docs/COMPLIANCE_INDIA.md`. Keep campaigns disabled until this is in place.

## 3. Secure tunnel for the local AI

Exotel (cloud) must reach your PC's WebSocket, but the AI runs locally. Expose **only** the stream endpoint,
token-protected:

```
# Example with cloudflared (free tier); replace with your tunnel of choice.
cloudflared tunnel --url http://127.0.0.1:8765
# Your public URL becomes e.g. https://<random>.trycloudflare.com
# StreamUrl (wss):   wss://<random>.trycloudflare.com/api/v1/exotel/stream
```

Never expose the backend without the stream token. The endpoint refuses any connection without the correct
`EXOTEL_STREAM_TOKEN`.

## 4. Environment variables (credentials live here, never in the app or git)

Set these for the SELL AGENT process (Windows: System → Environment Variables, or a `.env` you keep private):

```
EXOTEL_API_KEY=...
EXOTEL_API_TOKEN=...
EXOTEL_SID=...
EXOTEL_SUBDOMAIN=api.exotel.com        # or api.in.exotel.com
EXOTEL_STREAM_TOKEN=<a long random secret>   # must match the ?token= in your StreamUrl
```

## 5. Configure the app

In **SELL AGENT → Devices → Telephony provider**:
- **Enable the telephony provider** = on
- **Provider** = Exotel AgentStream
- **Caller ID / ExoPhone** = your ExoPhone (NOT your Jio number unless Exotel confirmed it)
- **AgentStream sample rate** = 8000 (default) or 16000
- **Public StreamUrl** = `wss://<your-tunnel>/api/v1/exotel/stream?token=<EXOTEL_STREAM_TOKEN>`

Click **Save**, then **Test provider readiness** — it should report the Exotel route READY to dial (credentials
present, stream URL set). It will still say autonomous is blocked until the release gate opens (step 7).

## 6. Local AI models

```
python scripts/download_models.py --whisper small --piper hi_IN-priyamvada-medium en_US-lessac-medium --yes
```

## 7. Real consented test call → open the gate

1. With a **consenting participant** on a designated test number, place a single call via the app on the `exotel`
   route.
2. Verify: the call connects, Priya greets (disclosing she is an AI), the participant's speech reaches Priya, and
   Priya's reply is heard by the participant — in the **same** call, both directions.
3. Run the 15-point checks (Hindi, English, switching, barge-in, cancellation, hang-up, busy/no-answer/failed,
   emergency stop, opt-out, result saved, next-call progression, restart recovery).
4. Record the evidence and confirm the two-way audio in **Devices → Audio feasibility console**. Only then does
   the release gate open and autonomous calling become available — still subject to compliance.

## 8. Troubleshooting

- "provider not enabled / credentials missing" on the provider screen → check the env vars and that Enable is on.
- Exotel can't connect to the StreamUrl → the tunnel is down or the token in the URL doesn't match
  `EXOTEL_STREAM_TOKEN`.
- No audio one way → confirm the sample rate matches what Exotel is sending; check the StreamUrl `sample-rate`.
- Call refused by Exotel → caller-ID/campaign not approved, or DLT not registered.
