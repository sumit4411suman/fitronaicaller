# Blueprint coverage

Every box on the "SELL AGENT complete blueprint" mapped to where it is implemented and how it is verified.
**Verified** = automated test or CI build passes. **Needs device/PC** = code is complete but can only be proven on the
Samsung Galaxy S25 / Windows 11 PC / with downloaded models.

## 1. Windows 11 desktop application (PySide6)

| Blueprint item | Where | Status |
| --- | --- | --- |
| Dashboard & Analytics | `screens/dashboard.py`, `/reports/dashboard` (real counts, week-over-week comparisons, sentiment) | Verified (tests/ui) |
| Contacts CRM (CRUD) | `screens/contacts.py`, `contact_detail.py`, `/contacts` | Verified |
| CSV / XLSX Import & Export | `screens/import_export.py`, `/contacts/import/*`, `/contacts/export` | Verified |
| Campaign Management | `screens/campaigns.py`, `/campaigns` incl. Start / Pause / progress | Verified |
| Live Call Console | `screens/live_call.py`, `/calls/{id}/step`, summary, live transcription | Verified (transcription audio needs PC mic) |
| Follow-ups & Calendar | `screens/followups.py`, `/followups/calendar` | Verified |
| AI Model Settings | `screens/model_manager.py`, `/ai/catalog`, `/ai/models/pull` | Verified; model download needs internet once |
| Knowledge Base (RAG) | `screens/knowledge.py`, `/knowledge` (txt/md/csv/pdf/docx) | Verified |
| Reports & Analytics | `screens/analytics.py`, `/reports/generated` (daily JSON/CSV/HTML) | Verified |
| Device Pairing | `screens/devices.py`, `/devices/pairing/*` | Verified (phone side needs S25) |
| Settings & Backup | `screens/settings.py`, `backup.py`, `/settings`, `/backup` | Verified |
| Users, roles, sign-in | Settings > Users & Roles, header Switch user | Verified |

## 2. Local backend server (FastAPI + Python)

| Blueprint item | Where | Status |
| --- | --- | --- |
| Authentication & Pairing API | `api/v1/auth.py`, `devices.py` | Verified |
| Contacts & CRM API | `api/v1/contacts.py` | Verified |
| Campaign Management API | `api/v1/campaigns.py` | Verified |
| Call Control API | `api/v1/calls.py` | Verified |
| AI & Knowledge API | `api/v1/ai.py`, `knowledge.py`, `speech.py`, `transcribe.py` | Verified |
| Reports & Settings API | `api/v1/reports.py`, `settings.py`, `system.py` | Verified |
| Campaign Engine | `workers/jobs.py::CampaignEngineWorker` | Verified |
| Call Queue Manager | `services/call_jobs.py`, `workers/jobs.py::CallQueueWorker` | Verified |
| Contact Eligibility | `services/eligibility.py` | Verified |
| Conversation Orchestrator | `sellagent_ai/conversation/engine.py` + `/calls/{id}/step` | Verified |
| Follow-up Scheduler | `workers/jobs.py::FollowupWorker` (reminders, scheduled jobs, auto follow-ups) | Verified |
| Reporting & Analytics | `services/reports.py`, `workers/jobs.py::ReportWorker` | Verified |
| Audit & Logging | `services/audit.py`, rotating `backend.log` | Verified |
| Device Pairing (Token) | `security/pairing.py`, `security/tokens.py` | Verified |
| JWT Authentication | `security/auth.py` (HS256, 12 h, revocable via token_version) | Verified |
| Role & Permission | admin / manager / operator / viewer enforced on every router | Verified |
| Encryption (DPAPI) | `security/secret_store.py` (token, DB key, JWT secret) | Code path runs on Windows CI |
| Consent & Opt-out | `services/contacts.py`, `suppression.py`, conversation opt-out | Verified |
| Secure WebSocket (WSS) | `lan.py` TLS + pinned fingerprint on the phone | Verified (TLS); phone pinning needs S25 |
| Audit Trail | `audit_events` table, `/audit` | Verified |
| AI Worker (LLM + RAG) | `workers/ai.py` single-slot executor, cancel, `/ai/chat-stream` | Verified with a stub model; real model needs Ollama |
| Speech Worker (STT + TTS) | `workers/ai.py` speech executor, `/ws/transcribe`, `/speech/*` | Verified with a stub STT; real models need download |
| Call Queue Worker | `CallQueueWorker` | Verified |
| Report Worker | `ReportWorker` | Verified |

## 3. Samsung Android companion app (Kotlin)

| Blueprint item | Where (`apps/android-companion`, shared `core/`) | Status |
| --- | --- | --- |
| Secure Device Pairing | `core/ui/PairingScreen.kt`, `core/net/PairingClient.kt`, `FingerprintTrust.kt`, Keystore storage | CI build passes; needs S25 |
| Receive Call Commands | `core/net/DeviceSocket.kt`, `companion/CallController.kt` | CI build passes; needs S25 |
| Dial / End Call (permitted) | `TelecomManager.placeCall`, InCallService disconnect | CI build passes; needs S25 |
| Call State Events (real-time) | `core/telecom/CallMonitor.kt`, `SellAgentInCallService.kt` | CI build passes; needs S25 |
| Audio Route Diagnostics | `core/ui/AudioToolsScreens.kt` | CI build passes; needs S25 |
| Microphone & Speaker Test | `core/ui/AudioToolsScreens.kt` | CI build passes; needs S25 |
| Foreground Service | `core/service/ConnectionForegroundService.kt` | CI build passes; needs S25 |
| Battery Optimization | `core/power/BatteryOptimization.kt`, `core/ui/BatteryScreen.kt` | CI build passes; needs S25 |
| Permission Management | `core/ui/PermissionsScreen.kt` | CI build passes; needs S25 |
| Manual Calling Mode | human-assisted Dial confirmation; autonomous refused | CI build passes; needs S25 |
| Logs & Troubleshooting | `core/log/AppLog.kt`, `LogsScreen.kt`, `TroubleshootingScreen.kt` | JVM tests pass; needs S25 |
| Separate audio feasibility test app | `apps/android-audio-diagnostic` (18-step plan) | CI build passes; needs S25 |

## 4. Local AI engine (CPU, 16 GB RAM, no GPU)

| Blueprint item | Where | Status |
| --- | --- | --- |
| Qwen3 1.7B (recommended) | default `ai.llm_model = qwen3:1.7b` (Apache-2.0) | Needs Ollama + download, benchmark script ready |
| Qwen2.5 3B (alternative) | in catalogue; **non-commercial licence**, pull needs explicit acknowledgement | Needs permission for commercial use |
| llama.cpp (GGUF 4-bit) | `sellagent_ai/llm/llamacpp.py` | Needs llama-server + GGUF |
| CPU inference, Hindi / English, streaming response | Ollama/llama.cpp streaming, `/ai/chat-stream` SSE | Verified with stub; real speed measured by `sellagent_ai.benchmark` |
| faster-whisper base (recommended) / small (optional) | default `ai.whisper_model = base` | Needs model download |
| Voice Activity Detection | `sellagent_speech/vad.py` | Verified |
| Real-time transcription | `/ws/transcribe` (consent-gated, audio not stored) | Verified with stub STT |
| Piper / ONNX voices (English default, Hindi validated) | `sellagent_speech/tts.py`, `hi_IN-pratham-medium` / `priyamvada` listed | Needs voice download; Hindi quality must be listened to |
| SQLite FTS5, document upload PDF / DOCX / TXT, chunking & search | `sellagent_kb` | Verified |
| FITRON product knowledge, FAQs, pricing, objections | seeded approved facts; FAQs/objections added through the review workflow | Verified (only approved facts are spoken) |
| Deterministic state machine, Hindi/English scripts, objection handling | `sellagent_ai/conversation` | Verified |
| Sentiment & intent detection | `sellagent_ai/sentiment.py`, `ConversationEngine.classify_intent` | Verified |
| Next step & follow-up | outcomes, follow-up creation, automatic follow-ups | Verified |

## 5. Telecom layer (real device)

| Blueprint item | Status |
| --- | --- |
| Jio SIM Wi-Fi Calling, two-way audio, tested on real device | **Not tested yet**. The audio feasibility app and evidence pipeline are ready; autonomous calling stays locked by the release gate until both audio directions pass on the S25. Public Android APIs do not give normal apps call audio (see `docs/TELECOM_FEASIBILITY.md`), so the expected result is human-assisted calling. |

## 6. Database (SQLite, local)

All 19 blueprint tables exist (`contacts`, `contact_permissions`, `suppression_list`, `campaigns`, `campaign_contacts`, `call_jobs`,
`calls`, `call_events`, `transcripts`, `call_notes`, `followups`, `knowledge_documents`, `knowledge_chunks`, `ai_runs`,
`paired_devices`, `audio_tests`, `settings`, `audit_events`, `schema_version`) plus `users`. Two Alembic migrations, tested
upgrade/downgrade. **Encrypted at rest** with SQLCipher AES-256 (verified: the database file contains no readable contact data).

## 7. Data flow

Desktop -> REST/WebSocket -> FastAPI -> SQLite and AI engine; backend -> WSS -> Android -> Jio network. Verified end to end
with a real server process (`tests/e2e`) and the device WebSocket tests; the phone-to-network leg needs the S25.

## 8. Security & privacy

| Blueprint item | Status |
| --- | --- |
| 100% local processing (no cloud AI) | Verified: no external calls unless `privacy.allow_external_network` is turned on for downloads |
| Encrypted WebSocket (WSS) | Verified (TLS LAN listener) |
| Device pairing with token | Verified |
| Data stored in local SQLite (encrypted) | Verified (SQLCipher) |
| Windows DPAPI for secrets | Implemented; exercised on the Windows CI runner |
| Android Keystore for device secrets | CI build passes; needs S25 |
| Consent & opt-out enforcement | Verified |
| Audit logs for all actions | Verified |
| No unauthorized data sharing | Verified (no telemetry; exports are explicit) |
| GDPR / DPDP ready | Controls implemented; legal obligations listed in `docs/COMPLIANCE_INDIA.md` |

## 9. Testing & deployment

| Phase | Status |
| --- | --- |
| 1 Android calling feasibility (real device tests Jio + S25) | Apps and procedure ready; **waiting for the S25 run** |
| 2 Backend & CRM | Done, 159 automated tests |
| 3 Local AI & speech | Done; benchmark on the target PC pending |
| 4 Full integration | Done in automated end-to-end tests; real-call integration pending the S25 |
| 5 Packaging (Windows installer + Android APK) | CI builds both APKs and the Windows installer |
| 6 Production release | Pending code signing, the S25 audio results and the DLT/telemarketer route for promotional calls |
