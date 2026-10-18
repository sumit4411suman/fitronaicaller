# Release notes

## 0.1.0 (2026-10-18) - first engineering release

**Delivered and verified by automated tests**
* Local backend (FastAPI, SQLite WAL/FK/FTS5, Alembic) with 88 endpoints and authenticated WebSockets.
* CRM: contacts, dedupe, CSV/XLSX import with preview/mapping/duplicate policy, export, archive, consent records,
  opt-out, suppression list.
* Campaigns with authorisation lifecycle; call jobs with eligibility gating, idempotency, dispatch, cancel, emergency stop;
  follow-ups; dashboard and reports from live data only.
* Knowledge base with approval/versioning/expiry, injection screening, FTS5 retrieval with citations; FITRON seed facts
  (list price Rs 1,999/month approved; first-100 offer pending configuration and approval).
* Conversation engine: 20-state machine, Hindi/English scripts, guardrails, local LLM adapters (Ollama, llama.cpp),
  benchmark CLI; speech wrappers (faster-whisper, Piper, VAD) with local diagnostics labelled as simulated.
* Pairing (time-limited codes, mutual approval, hashed one-time tokens, revocation), TLS LAN listener with pinned
  fingerprint, protocol v1.0 with exported JSON Schema.
* Encrypted backup/restore, retention, audit log, DPAPI-protected local token, settings with a release gate that only
  operator-confirmed real-device audio evidence can open.
* Brand package: FITRON gold-on-black theme for desktop and Android.

**Delivered as source/scripts, not executed in this release**
* Windows desktop app (see `docs/DESKTOP_APP.md` for what the offscreen UI tests cover).
* Android companion and audio feasibility apps (CI build; no device run).
* Windows installer build (PyInstaller + Inno Setup, Windows CI job).
* Model downloads, LLM/STT/TTS benchmarks, offline proof on the target PC.
* All 16 real-device audio feasibility steps: NOT TESTED.

**Defaults changed after compliance research**: quiet hours 21:00-10:00 (TRAI window 10:00-21:00); Qwen2.5-3B dropped
(non-commercial licence); Piper flagged GPL.

Versioning: app `0.1.0`, protocol `1.0`, schema revision `0e31780f89ea`.
