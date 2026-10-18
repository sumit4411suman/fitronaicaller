# Test report

Environment for everything marked *automated*: Linux x86-64 cloud container, Python 3.12.3, 4 vCPU, 15 GB RAM, no GPU,
no Windows machine, no Android device, no model downloads (Hugging Face and Ollama registries blocked). Date: 2026-10-18.

Legend: **automated** (runs in CI), **simulated** (fakes, never evidence of cellular audio), **emulator**, **real-device**,
**NOT TESTED**.

## Automated suite (actual run)

Command: `python -m pytest tests/unit tests/integration tests/e2e -q`

```
99 passed in 19.83s
```

| File | Tests | What it proves |
| --- | --- | --- |
| tests/unit/test_protocol.py | 6 | envelope round trip, strict payloads, version check, capability defaults, schema export |
| tests/unit/test_phone_and_language.py | 13 | Indian number normalisation/validation, Hindi/English detection |
| tests/unit/test_state_machine.py | 9 | 20 states, happy path, invalid transitions, consent/authorisation gates, opt-out and emergency-stop overrides, terminal states |
| tests/unit/test_guardrails_and_engine.py | 13 | approved price passes; Rs 499, 70%, guarantees, integrations, testimonials, support claims rejected; greeting disclosure; LLM output failing guardrails falls back to script; Hindi opt-out flow; unknown question gets "no confirmed information" |
| tests/unit/test_vad_and_speech.py | 4 | energy VAD segments/onset, resampling, graceful absence of optional engines |
| tests/unit/test_security_primitives.py | 7 | token hashing, pairing code format, TTL/attempt exhaustion, mutual approval + one-time token, window hijack prevention, secret file 0600, audit redaction |
| tests/integration/test_contacts_api.py | 8 | CRUD/search/sort/archive/delete, validation, duplicates (409), consent + opt-out -> suppression, lift with justification, CSV/XLSX import preview/commit/export, formula-injection guard |
| tests/integration/test_calls_and_campaigns.py | 10 | campaign lifecycle and gate, membership exclusion, blocked without consent / in quiet hours, full manual call flow with conversation steps and cited price, opt-out mid-call stops everything, emergency stop cancels and blocks, autonomous + android route blocked without evidence, rate limits, cancel/requeue |
| tests/integration/test_knowledge_api.py | 7 | seeded facts, offer pending, Hindi retrieval, injection flags block approval, untrusted import + versioning, expiry, simulation labelled, AI status without provider |
| tests/integration/test_security_and_devices.py | 9 | 401s everywhere, WS rejections, pairing wrong code/rejection, pair-authenticate-revoke, device WebSocket heartbeat/dedupe/malformed/call.request ack/call.state/emergency stop, release gate rules, settings validation, health WAL/FK/FTS, audit has no tokens, token rotation |
| tests/integration/test_backup_and_migrations.py | 5 | Alembic upgrade/downgrade/upgrade, FK enforcement, transactional import rollback, encrypted backup round trip + wrong passphrase + path rejection + restore, retention |
| tests/e2e/test_real_server.py | 4 | real uvicorn subprocess: health, token file protection and TLS files, desktop WebSocket receives emergency stop, bad WS token rejected, OpenAPI drift check |
| tests/device/* | 17 | **skipped = NOT TESTED** (evidence checkers for the 16 real-device steps + gate consistency) |
| tests/ui/* | see docs/DESKTOP_APP.md | offscreen Qt |

Lint: `ruff check services packages tests scripts` clean. Brand sync: `scripts/check_brand_sync.py` passes.

## Bugs found and fixed by the tests
* New calls started in `eligibility_check`, so the operator's "Connected" action was refused (fixed: dispatch sets `dial_request`, connected walks the machine).
* Injection screen missed "ignore all previous instructions" (regex widened).
* Two backups in the same second overwrote each other (millisecond timestamps).

## Target-hardware results (Windows 11, 16 GB, CPU only)

NOT TESTED in this session. Fill in from `python -m sellagent_ai.benchmark ...` and `scripts/offline_check.py`:

| Metric | qwen3:1.7b | qwen3:4b |
| --- | --- | --- |
| cold load (ms) | | |
| first token (ms, median) | | |
| tokens/s (median) | | |
| Ollama RSS after load (MB) | | |
| Hindi language-match rate | | |
| English guardrail pass rate | | |
| JSON validity rate | | |

| Speech | whisper small | Piper en | Piper hi |
| --- | --- | --- | --- |
| load ms / latency ms | | | |
| loopback word overlap (SIMULATED) | | | |

App startup time, idle RAM, retrieval latency, DB query timings: to be recorded with the desktop app on the target PC.

## Real-device audio feasibility (Samsung Galaxy S25, Jio SIM, Wi-Fi Calling)

All 18 steps: **NOT TESTED** (no device in this session). Expected outcomes from documented APIs and the full template are
in `docs/TELECOM_FEASIBILITY.md`. Release gate state: **closed**; autonomous calling disabled.

| Test ID | Date | Phone / Android / App | Network | Step | Direction | Expected | Actual | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AFT-(pending) | | SM-S931B / 15 / 0.1.0 | Jio VoWiFi + Wi-Fi LAN | pairing | none | pass | | | NOT TESTED |
| | | | | call_state_reporting | none | pass (coarse without default dialer, detailed with) | | | NOT TESTED |
| | | | | outgoing_call | none | pass | | | NOT TESTED |
| | | | | remote_speech_capture | inbound | BLOCKED (VOICE_CALL/DOWNLINK privileged); only acoustic leakage | | | NOT TESTED |
| | | | | generated_speech_transmission | outbound | acoustic only (speaker -> handset mic) | | | NOT TESTED |
| | | | | simultaneous_two_way | both | degraded by AEC/echo | | | NOT TESTED |
| | | | | route_earpiece / speaker / bluetooth / wired | none | pass when default dialer; otherwise partial | | | NOT TESTED |
| | | | | latency_echo_quality | both | unknown | | | NOT TESTED |
| | | | | screen_locked | none | pass with FGS phoneCall/microphone | | | NOT TESTED |
| | | | | wifi_interruption | none | reconnect + replay | | | NOT TESTED |
| | | | | hindi_phrases / english_phrases | both | depends on TTS voice | | | NOT TESTED |
| | | | | jio_wifi_calling | none | same restrictions as cellular | | | NOT TESTED |
