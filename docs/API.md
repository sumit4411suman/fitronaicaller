# Local API

Base URL `http://127.0.0.1:8765/api/v1`. Interactive docs at `http://127.0.0.1:8765/docs`; the committed spec is
`docs/api/openapi.json` (regenerate with `python -m sellagent_backend.main --export-openapi docs/api/openapi.json`; CI fails if stale).

Authentication: `Authorization: Bearer <local token>` (built-in owner, admin) or `Bearer <JWT>` from `/auth/login` for
signed-in users. Each router checks `<area>:read` for GET and `<area>:write` otherwise against the role
(admin, manager, operator, viewer; see `GET /auth/roles`). 403 means the role lacks the permission. The token is created on first run at
`<data dir>/local_api_token` (DPAPI-protected on Windows). Device endpoints use the device token issued at pairing.
Every response carries `X-Request-ID`; errors are `{code, error, request_id, detail?}`.

| Group | Endpoints (summary) |
| --- | --- |
| health | `GET /health/ping` (public liveness), `GET /health` (includes database encryption state) |
| auth | `POST /auth/login` (username + PIN -> JWT, public), `POST /auth/logout`, `GET /auth/whoami`, `GET /auth/roles`, `POST /auth/rotate-local-token` |
| users | admin only: list, create, patch (role/active/display name), reset PIN, delete |
| system | `GET /system/workers`, `POST /system/workers/{name}/run`, `POST /system/workers/{name}/enabled`, `POST /system/ai-jobs/{id}/cancel` |
| contacts | list/search/sort/page, create, get, patch, delete (archive or `hard=true`), unarchive, permissions (list/add), opt-out, eligibility, duplicates, export (csv/xlsx), import upload/preview/commit, stages |
| suppression | list, add, lift (justification required), check |
| campaigns | list, create, get, patch, transition, start, pause, add contacts, members, stats (with progress) |
| call-jobs | list, create (idempotent), get, queue, dispatch, cancel, routes, emergency-stop |
| calls | history, outcomes, get (events/transcript/notes), connected, no-answer, step (conversation, with sentiment), transcript, notes, outcome, summary, transcription-consent, cancel |
| followups | list, calendar (month view), create, complete |
| knowledge | list, categories, create, import (.txt/.md/.csv), retrieve, screen, get, approve, reject, supersede, delete |
| ai | status, catalog, models/pull (explicit acknowledgement + network setting; licence acknowledgement for qwen2.5), chat-test, chat-stream (SSE), simulate (labelled SIMULATION), runs |
| speech | status, tts, stt (WAV upload), loopback (SIMULATED) |
| reports / audit | dashboard (with comparisons and sentiment), campaign report, generated daily reports (list, generate, download); audit list with filters |
| settings | get, patch (typed/validated; release-gate keys read-only), release-gate, release-gate/recompute, retention/run |
| backup | list, create (passphrase when encryption on), verify, restore (typed confirmation) |
| devices | pairing open/close/status/decide, list, connected, revoke, delete; device-facing: pair, pair/result, me |
| audio-tests | plan (16 steps), list, record, confirm, delete, report |
| ws | `/ws/desktop?token=` (events + emergency stop; local token or JWT), `/ws/device` (Bearer device token), `/ws/transcribe` (PCM16 audio in, transcript out) |

## WebSocket messages

All frames are protocol envelopes (`packages/shared-protocol/schema`). Device -> backend: `session.heartbeat`,
`session.capabilities`, `call.state`, `audio_test.event`, `audio_test.result`, `safety.emergency_stop`, `session.reconnect`,
`error`, `ack`. Backend -> device: `session.heartbeat_ack`, `call.request` (must be acked), `call.cancel`,
`safety.emergency_stop`, `session.reconnect_ack`, `ack`, `error`. The backend de-duplicates by `message_id`, answers
duplicates with `ack`, replays queued messages after `session.reconnect`, and expires undelivered `call.request`s after
10 s (job fails with "device did not acknowledge").

Desktop event envelopes (`type: "event"`, payload `{name, data}`): `queue.ready`, `queue.blocked`, `campaign.jobs_created`,
`campaign.completed`, `followup.due`, `followup.created`, `report.ready`, `worker.error`. Devices ignore unknown types.
