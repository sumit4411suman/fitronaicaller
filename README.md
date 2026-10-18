# SELL AGENT

Local, privacy-first, AI-assisted sales calling platform for selling **FITRON** gym accounting software to gym businesses in India.

* Windows 11 desktop app (PySide6) + local FastAPI backend + SQLite, all on your PC. No paid AI APIs; local LLM, speech and retrieval.
* Android companion app and a separate **Audio Feasibility Test** app for a Samsung Galaxy S25 on a Jio SIM with Wi-Fi Calling.
* Hindi and English scripts, approved-facts-only answers, consent/suppression/opt-out controls, emergency stop everywhere.
* Theme: the FITRON logo, gold on near-black, identical in the desktop app and both Android apps (`packages/brand`).

> **Release gate.** Autonomous cellular AI calling is **disabled** and cannot be switched on until operator-confirmed, real-device tests prove both remote-audio capture and AI-speech transmission through supported Android interfaces. Until then SELL AGENT runs in **human-assisted** mode: the operator dials and speaks, the app supplies eligibility checks, scripts, approved facts, transcripts, outcomes and follow-ups. See `docs/TELECOM_FEASIBILITY.md` and `docs/TEST_REPORT.md` for what has and has not been demonstrated.

## Repository layout

| Path | Contents |
| --- | --- |
| `apps/windows-desktop/` | PySide6 desktop application (22 screens) |
| `apps/android-companion/` | Kotlin/Compose companion app (pairing, call requests, call state, emergency stop) |
| `apps/android-audio-diagnostic/` | Kotlin/Compose audio feasibility test app (16-step real-device test plan) |
| `services/local-backend/` | FastAPI backend: CRM, eligibility, campaigns, call jobs, pairing, WebSocket hub, backup |
| `services/ai-engine/` | LLM adapters (Ollama, llama.cpp), conversation state machine, guardrails, scripts, benchmark |
| `services/speech-engine/` | faster-whisper STT, Piper TTS, VAD, local diagnostics |
| `services/knowledge-base/` | FITRON knowledge base: approval workflow, FTS5 retrieval, injection screening |
| `packages/shared-protocol/` | Versioned Windows<->Android message schemas (Pydantic + JSON Schema + Kotlin) |
| `packages/brand/` | Brand tokens, logo mark, Qt stylesheet, Android theme |
| `database/migrations/` | Alembic migrations |
| `tests/` | unit, integration, e2e (real server process), ui, device (evidence checkers) |
| `scripts/` | setup, run, model download, offline check, Windows build/installer |
| `docs/` | architecture, API, security, compliance, telecom feasibility, test report, limitations, troubleshooting |
| `models/README.md` | model inventory, sizes, licences |
| `LICENSES/` | dependency and model licence inventory |

## Quick start (Windows 11, Python 3.12)

```powershell
git clone <this repo> ; cd -futuremillionaire
.\scripts\setup_windows.ps1            # creates .venv, installs pinned deps, runs the automated tests
.\scripts\run_desktop.ps1              # launches the desktop app (starts the backend automatically)
```

Local AI (optional, but needed for LLM/speech features):

```powershell
winget install Ollama.Ollama           # or https://ollama.com/download/windows
.\.venv\Scripts\pip install -r requirements-speech.txt
.\.venv\Scripts\python scripts\download_models.py --llm qwen3:1.7b --whisper small --piper en_US-lessac-medium --yes
.\.venv\Scripts\python -m sellagent_ai.benchmark --models qwen3:1.7b qwen3:4b --out docs\benchmarks\llm.json
# disconnect from the network, then:
.\.venv\Scripts\python scripts\offline_check.py
```

Full instructions: `docs/SETUP_WINDOWS.md`, `docs/DESKTOP_APP.md`, `docs/ANDROID_APPS.md`.

## Status of this release (0.1.0)

| Area | Status | Evidence |
| --- | --- | --- |
| Backend, data layer, migrations, CRM, import/export, backup/restore | Implemented | 95 automated tests pass (`docs/TEST_REPORT.md`) |
| Eligibility, consent, suppression, opt-out, quiet hours, rate limits, emergency stop | Implemented | integration tests |
| Pairing, device tokens, revocation, TLS LAN listener, WebSocket hub | Implemented | integration + e2e tests |
| Knowledge base, approved pricing, guardrails, state machine, Hindi/English scripts | Implemented | unit + integration tests |
| Local LLM / STT / TTS adapters | Implemented, **not benchmarked** here | no model downloads possible in the build environment |
| Desktop app | see `docs/DESKTOP_APP.md` | offscreen UI tests |
| Android apps | source + CI build | **not compiled or run on a device in this session** |
| Cellular two-way audio | **NOT TESTED** | release gate closed; real-device procedure in `docs/TELECOM_FEASIBILITY.md` |
| Windows installer | build scripts + CI workflow | not produced in this Linux session |

Everything marked NOT TESTED is a gap, not a claim.
