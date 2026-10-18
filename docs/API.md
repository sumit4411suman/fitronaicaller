# Local API

Base URL `http://127.0.0.1:8765/api/v1`. Interactive docs at `http://127.0.0.1:8765/docs`; the committed spec is
`docs/api/openapi.json` (regenerate with `python -m sellagent_backend.main --export-openapi docs/api/openapi.json`; CI fails if stale).

Authentication: `Authorization: Bearer <local token>` for all operator endpoints. The token is created on first run at
`<data dir>/local_api_token` (DPAPI-protected on Windows). Device endpoints use the device token issued at pairing.
Every response carries `X-Request-ID`; errors are `{code, error, request_id, detail?}`.

| Group | Endpoints (summary) |
| --- | --- |
| health | `GET /health/ping` (public liveness), `GET /health` |
| auth | `GET /auth/whoami`, `POST /auth/rotate-local-token` |
| contacts | list/search/sort/page, create, get, patch, delete (archive or `hard=true`), unarchive, permissions (list/add), opt-out, eligibility, duplicates, export (csv/xlsx), import upload/preview/commit, stages |
| suppression | list, add, lift (justification required), check |
| campaigns | list, create, get, patch, transition (draft/authorized/active/paused/completed/archived), add contacts, members, stats |
| call-jobs | list, create (idempotent), get, queue, dispatch, cancel, routes, emergency-stop |
| calls | history, outcomes, get (events/transcript/notes), connected, no-answer, step (conversation), transcript, notes, outcome, cancel |
| followups | list, create, complete |
| knowledge | list, categories, create, import (.txt/.md/.csv), retrieve, screen, get, approve, reject, supersede, delete |
| ai | status, catalog, models/pull (explicit acknowledgement + network setting), chat-test, simulate (labelled SIMULATION), runs |
| speech | status, tts, stt (WAV upload), loopback (SIMULATED) |
| reports / audit | dashboard, campaign report; audit list with filters |
| settings | get, patch (typed/validated; release-gate keys read-only), release-gate, release-gate/recompute, retention/run |
| backup | list, create (passphrase when encryption on), verify, restore (typed confirmation) |
| devices | pairing open/close/status/decide, list, connected, revoke, delete; device-facing: pair, pair/result, me |
| audio-tests | plan (16 steps), list, record, confirm, delete, report |
| ws | `/ws/desktop?token=` (events + emergency stop), `/ws/device` (Bearer device token) |

## WebSocket messages

All frames are protocol envelopes (`packages/shared-protocol/schema`). Device -> backend: `session.heartbeat`,
`session.capabilities`, `call.state`, `audio_test.event`, `audio_test.result`, `safety.emergency_stop`, `session.reconnect`,
`error`, `ack`. Backend -> device: `session.heartbeat_ack`, `call.request` (must be acked), `call.cancel`,
`safety.emergency_stop`, `session.reconnect_ack`, `ack`, `error`. The backend de-duplicates by `message_id`, answers
duplicates with `ack`, replays queued messages after `session.reconnect`, and expires undelivered `call.request`s after
10 s (job fails with "device did not acknowledge").
