# Architecture

## Components

```
+--------------------------+        HTTP 127.0.0.1:8765 / WS          +---------------------------+
| Windows desktop (PySide6)| <--------------------------------------> | Local backend (FastAPI)   |
|  22 screens, emergency   |                                          |  SQLite (WAL, FK, FTS5)   |
|  stop, live console      |                                          |  services, hub, adapters  |
+--------------------------+                                          +------+--------------+-----+
                                                                             |              |
                                            opt-in LAN listener  wss://<pc>:8766 (self-signed, pinned)
                                                                             |              |
                                                     +-----------------------+--+    +------+------------------+
                                                     | Android companion        |    | Audio feasibility test   |
                                                     | pairing, call.request,   |    | 16-step real-device plan |
                                                     | call.state, emergency    |    | results -> audio_tests   |
                                                     +--------------------------+    +--------------------------+
                                                                 |
                                                       Telecom (Jio SIM, VoWiFi) -- only via documented Android APIs
```

Local AI sits beside the backend as separate local processes/libraries: Ollama or llama-server (LLM), faster-whisper (STT),
Piper (TTS). The backend talks to them over localhost only and never to the internet unless the user enables
`privacy.allow_external_network` for a model download.

## Backend modules (`services/local-backend/sellagent_backend`)

| Module | Responsibility |
| --- | --- |
| `config.py` | settings (env `SELLAGENT_*`), data directory, safe defaults (localhost bind, LAN off, human-assisted) |
| `db/` | engine with pragmas, ORM models (19 tables), programmatic Alembic runner |
| `security/` | token hashing, pairing window (TTL, attempts, mutual approval), DPAPI/0600 secret file, self-signed TLS |
| `services/` | contacts, phone, import/export, suppression, eligibility, campaigns, call_jobs, followups, reports, backup, settings, audit |
| `telecom/` | `ManualAdapter` (human-assisted) and `AndroidCompanionAdapter` (dial via phone), `audio_gate_status` |
| `ws/hub.py` | device/desktop WebSocket registry, de-dup, call-state application, emergency stop fan-out, reconnect replay |
| `api/v1/` | REST routers + WebSocket endpoints; OpenAPI at `/docs`, spec committed to `docs/api/openapi.json` |
| `lan.py` | second uvicorn server for device routes only, started/stopped by the housekeeping task |
| `app.py` | factory, lifespan (migrate, seed knowledge, token), request ids, error envelopes |

## Data flow for a human-assisted call

1. Operator picks a contact; `eligibility.check` evaluates emergency stop, number type, suppression, opt-out, consent,
   campaign authorisation, quiet hours, rate limits, attempts, mode/route support. The result is stored on the call job.
2. `call_jobs.dispatch` mints a one-time authorization token (stored hashed), creates the `calls` row in `dial_request`.
3. Manual route: the operator dials on their phone and presses **Connected**; Android route: the backend sends `call.request`
   over the WebSocket and waits for the device's `ack`; the device then reports `call.state` events.
4. Each `POST /calls/{id}/step` records the prospect's utterance, runs the state machine with safety context from the DB
   (consent, opt-out, emergency stop), retrieves approved facts, optionally asks the local LLM to rephrase, runs guardrails,
   and stores the agent line with knowledge references.
5. Outcome -> lead stage, follow-up, suppression (wrong number / opt-out), audit.

## Conversation engine (`services/ai-engine`)

Explicit 20-state machine (`conversation/states.py`) with transition table and guards; the LLM only rephrases approved
script lines and is overruled by `guardrails.check_reply` (approved numbers only, forbidden-claim lexicon, identity and
automation disclosure in the greeting, no pressure after opt-out). If no LLM is available the approved script is spoken.

## Knowledge base (`services/knowledge-base`)

Documents -> chunks -> FTS5 external-content index kept in sync by triggers. Only `approved`, effective, non-expired
documents are retrievable in production paths. Imports are untrusted and screened for prompt-injection patterns; approval of
flagged documents requires explicit acknowledgement. Every agent line that uses a fact carries `kb:<doc>#v<version>:c<chunk>`.

## Protocol (`packages/shared-protocol`)

Envelope `{protocol_version, type, message_id, sent_at, in_reply_to, payload}`; strict payloads; 19 message types covering
pairing, heartbeat, capabilities, call request/state/cancel, audio-test events/results, emergency stop, reconnect, error, ack.
JSON Schema is exported to `schema/` and checked for drift in CI.

## Security boundaries

* Main API binds to 127.0.0.1 only (refuses other hosts). Desktop authenticates with a random local token stored
  DPAPI-protected (Windows) / 0600 (other).
* LAN listener is opt-in, TLS with a self-signed certificate whose SHA-256 fingerprint the phone pins; exposes only pairing
  and device WebSocket routes; pairing codes expire in 5 minutes with 5 attempts; tokens are hashed at rest and revocable.
* The LLM cannot touch consent, suppression, emergency stop or authorization: those live in the backend and the state machine.
* Autonomous mode is gated by `release_gate.autonomous_calling_allowed`, recomputed only from operator-confirmed real-device
  audio test rows (inbound and outbound).
