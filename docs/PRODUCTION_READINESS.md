# SELL AGENT production readiness — what's built vs. what you must supply

Status date: 2026-10-19. This tracks the production Windows AI-calling system against the spec. It is honest about
what is implemented and tested in this repo versus what genuinely needs your telephony account and a real call.

## Calling routes (modular telephony interface)

All routes share one `TelecomAdapter`/provider interface and the same local AI loop, and all sit behind the same
release gate. **The default path is your own Galaxy S25 on Jio — no paid provider is required** (see
`docs/JIO_DIRECT_CALLING.md`). Exotel is an **optional** cloud add-on, off by default.

| Route | What it is | State |
|---|---|---|
| `manual` | Human-assisted: operator dials, Priya suggests lines | Works today |
| `android_companion` | Paired phone (dial/state) over USB/Wi-Fi; no call audio on a non-rooted S25 | **Default.** Works for control; audio blocked (docs/S25_COMPATIBILITY.md, docs/JIO_DIRECT_CALLING.md) |
| `media_gateway` / AudioSocket | Asterisk/USB-modem/**Bluetooth or wired local audio** into the loop | Built + simulated-tested; needs a real route verified |
| `exotel` *(optional)* | Exotel AgentStream cloud telephony, bidirectional WebSocket audio | Optional/off by default; needs your Exotel account + a real call. Caller ID is an ExoPhone, NOT your Jio number |

A **USB-ADB diagnostic** (`scripts/adb_jio_diagnostic.py`, helpers in `telecom/adb.py`) proves the S25 control
path (dial/state/hangup) and honestly reports that ADB carries no call audio.

## The 16 required screens (desktop app, PySide6)

| # | Spec screen | In the app |
|---|---|---|
| 1 | Secure setup wizard | `setup` |
| 2 | Dashboard & system health | `dashboard` + `logs` |
| 3 | CRM contacts + import/export | `contacts`, `contact_detail`, `import_export` |
| 4 | Campaign & eligibility review | `campaigns`, `eligibility` |
| 5 | Call queue (start/pause/resume/stop) | `call_queue` |
| 6 | Current call status + live transcript | `live_call` |
| 7 | AI voice & model settings | `persona`, `models`, `settings` |
| 8 | FITRON knowledge base & scripts | `knowledge`, `scripts` |
| 9 | Call history & outcomes | `call_history` |
| 10 | Follow-up scheduler | `followups` |
| 11 | **Provider configuration & diagnostics** | **`provider` (new in this milestone)** |
| 12 | Audio latency & quality tests | `audio_tests`, `diagnostics` |
| 13 | Consent, suppression, opt-out | `suppression` |
| 14 | Analytics & reports | `analytics` |
| 15 | Logs, backups, recovery | `logs`, `backup` |
| 16 | Privacy & retention settings | `settings` |

All 16 are present (27 screens total). Every screen refreshes against the real backend and exposes its controls
(`tests/ui/test_screens.py`). No screen shows simulated calls or fabricated numbers as real activity.

## Call lifecycle

The spec's states map onto the implemented conversation state machine + call-job lifecycle: eligibility check →
ready → dispatch (DIALING/RINGING via provider callbacks) → connected → greeting → listening/thinking/speaking
loop → completing → completed, plus busy/no-answer/rejected/failed/cancelled/opted-out/handoff. The autonomous
loop runs the greeting→listen→think→speak turns with barge-in, opt-out and emergency stop, and only starts when a
real call is connected with a verified two-way audio path. Emergency stop halts new calls and cancels pending jobs
(`/call-jobs/emergency-stop`).

## Local AI (no paid AI API)

faster-whisper (STT), the local conversation engine (script mode works with no LLM; optional local LLM via
Ollama/llama.cpp), female Piper TTS, SQLite FTS5 knowledge base — all local. Benchmarks (RAM, model load, STT/LLM/
TTS latency, Hindi/English accuracy) on the 16 GB CPU-only PC are **not yet measured in this environment** (models
can't be downloaded in the build sandbox); run them on your PC with `tests/voice` and the persona/provider
screens, and record the numbers. Do not treat latency as real-time until measured.

## What is DONE in this milestone (Exotel)

- `telecom/exotel.py`: `ExotelProvider` + `ExotelStreamTransport` (bidirectional, re-chunked, bounded, barge-in).
- `api/v1/exotel_ws.py`: token-authenticated AgentStream WebSocket, fail-closed.
- `provider.*` settings, the `provider` desktop screen, eligibility + release-gate wiring, `exotel` route caps.
- Tests: `tests/integration/test_exotel.py` (encode/decode, re-chunk, caller-ID=ExoPhone, disabled-route refusal,
  fail-closed path, WebSocket bind + inbound audio) — all **simulated**.

## What YOU must supply before a real production call (not fakeable here)

1. **Exotel business account** with KYC; an **ExoPhone** (caller ID); **AgentStream** enabled; API credentials in
   the environment (`EXOTEL_API_KEY`, `EXOTEL_API_TOKEN`, `EXOTEL_SID`, `EXOTEL_STREAM_TOKEN`).
2. A **secure tunnel** exposing only `/api/v1/exotel/stream` (token-protected) so Exotel can reach your local AI.
3. **DLT/TRAI registration** and Exotel's written **caller-ID/campaign confirmation** (docs/COMPLIANCE_INDIA.md).
   Do not assume your Jio number is allowed as caller ID.
4. A **real consented test call**, then confirm the two-way audio in the audio-feasibility console to **open the
   release gate**. Until then autonomous calling stays disabled.
5. Local **model downloads** (`scripts/download_models.py`) and recorded **benchmarks** on your PC.

## Not fabricated

No successful provider call, approval, recording, installer, or benchmark is claimed. Simulated/local-test results
are labelled as such. Costs are paid and are yours to confirm (docs/EXOTEL_EVALUATION.md). A genuine phone call
through the provider, with Priya and the caller hearing each other and the result saved, remains the user-side
acceptance step this milestone sets up but does not itself perform.
