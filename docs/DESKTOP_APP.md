# SELL AGENT — Windows desktop app

PySide6 desktop client for the local SELL AGENT backend (FastAPI on `127.0.0.1:8765`). The app never talks to
the internet itself; every action is an authenticated HTTP call (or a WebSocket event) to the local backend.

* Package: `apps/windows-desktop/sellagent_desktop` (entry point `sellagent_desktop.main:main`)
* Theme: `packages/brand/qt/theme.qss`, loaded **verbatim** (plus a small supplement for app-specific roles that only
  uses brand colours). Layout follows the approved mockup: a dark gold chrome (`#0B0B0B` sidebar with the FITRON mark
  and the wordmark **SELL <span>AGENT</span>**), a white header and light content (`#F7F6F2`) with white cards.
  Gold `#D4AF37` is the only accent; the emergency stop and end-call buttons are the only red fills.
* Fonts: Segoe UI with fallbacks Segoe UI Variable, Noto Sans, **Noto Sans Devanagari, Nirmala UI**, Mangal, so
  Hindi (Devanagari) renders on a stock Windows 11 install (Nirmala UI ships with Windows).

## 1. Launching

### From a source checkout (Windows 11, PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt          # includes requirements-desktop.txt (PySide6-Essentials)
.\scripts\run_desktop.ps1                    # starts the backend child process + the desktop app
```

`run_desktop.ps1 -BackendUrl http://127.0.0.1:8765` attaches to a backend you started yourself
(`python -m sellagent_backend.main`). The same is possible with the environment variable `SELLAGENT_BACKEND_URL`.

### Installed build

Start **SELL AGENT** from the Start menu or the desktop shortcut. `SellAgent.exe` starts `sellagent-backend.exe`
(no console window) from the same folder and stops it when the app closes.

### What happens at startup

1. A splash screen is shown while `backend_process.py` checks `GET /api/v1/health/ping` on `127.0.0.1:8765`.
   If nothing answers it launches the backend child (`sys.executable -m sellagent_backend.main`, or the bundled
   `sellagent-backend.exe` when frozen) and waits up to 40 s. Child output goes to
   `%LOCALAPPDATA%\SellAgent\logs\backend-child.log`.
2. The local API token is read from `%LOCALAPPDATA%\SellAgent\local_api_token` (DPAPI-protected on Windows,
   `PLAIN1:` with 0600 permissions elsewhere) using the backend's own `secret_store` reader.
3. The desktop WebSocket `/api/v1/ws/desktop?token=…` is opened on a background thread (library `websockets`,
   since QtWebSockets is not part of PySide6-Essentials) and reconnects automatically with back-off.
4. If `general.operator_name` is still the default or the flag file `desktop_first_run_done` is missing, the
   first-run wizard opens.

No network request runs on the UI thread: every call goes through `api_client.call_async` (Qt thread pool). While a
request is running the screen shows "Loading…" at the top right and a busy cursor; errors appear in the header
notification area and status bar with the backend's `error` text and `code`.

Data directory: `%LOCALAPPDATA%\SellAgent` (override with `SELLAGENT_DATA_DIR`). It holds the SQLite database,
models, backups, logs, the local token and the TLS certificate for the LAN pairing listener.

## 2. Window anatomy

| Area | What it shows | Source |
| --- | --- | --- |
| Sidebar | Logo, wordmark, the 11 navigation items, **AI Engine** dark card | — |
| AI Engine card | provider + Online/Offline + configured model; CPU %; RAM used/total; "No GPU (CPU mode)" | `/ai/status`, `psutil` on this PC |
| Header search | `Ctrl+K`; Enter searches contacts (name, person, phone, city) | `/contacts?q=` |
| Chip **Local AI** | Online = the configured provider (Ollama/llama.cpp) answers; Offline otherwise | `/ai/status.available` |
| Chip **Backend** | Running / Unreachable; tooltip shows the live WebSocket link state | `/health/ping` |
| Chip **phone** | model of the most recently seen approved device + Connected / Not connected; "Phone: not paired" when none | `/devices`, `/devices/connected` |
| Operator | initials + `general.operator_name` | `/settings` |
| **EMERGENCY STOP** | always visible on every screen | see §4 |
| Red banner | shown while `calling.emergency_stop_active` is true | `/settings`, WS `safety.emergency_stop` |
| Status bar | backend version, connected device count, emergency stop state | polled every 10 s + WS events |

## 3. Screens

The sidebar has the 11 entries of the approved mockup. Entries with several screens show them as tabs; every
screen is also reachable programmatically with `navigate(<screen key>)` (used by buttons such as "Call" on a contact).

| Sidebar | Tabs (screen key) | Main endpoints |
| --- | --- | --- |
| Dashboard | `dashboard` | `/reports/dashboard`, `/calls`, `/campaigns`, `/ai/status`, `/speech/status`, `/knowledge?status=approved`, `/devices` |
| Contacts | Contacts (`contacts`), Contact detail (`contact_detail`), Eligibility & consent (`eligibility`) | `/contacts*`, `/contacts/{id}/permissions`, `/opt-out`, `/eligibility`, `/followups` |
| Campaigns | `campaigns` | `/campaigns*`, `/transition`, `/contacts`, `/stats`, `/settings/release-gate` |
| Call Console | Live call (`live_call`), Call queue (`call_queue`), Call history (`call_history`) | `/calls/*`, `/call-jobs/*` |
| Follow-ups | `followups` | `/followups*` |
| Reports | `analytics` | `/reports/dashboard`, `/reports/campaign/{id}`, `/calls` (CSV export) |
| Knowledge Base | `knowledge` | `/knowledge*` |
| AI Settings | AI model manager (`models`), Speech & AI diagnostics (`diagnostics`), Sales script editor (`scripts`) | `/ai/*`, `/speech/*`, `/knowledge` |
| Devices | Pairing (`devices`), Audio feasibility console (`audio_tests`) | `/devices/*`, `/audio-tests/*`, `/settings/release-gate` |
| System Status | Health, logs & audit (`logs`), Workers (`workers`), Backup & restore (`backup`) | `/health`, `/audit`, `/system/workers*`, `/backup*` |
| Settings | Privacy & calling settings (`settings`), Users & Roles (`users`, admin only), Suppression & opt-out (`suppression`), Import / export (`import_export`), Setup wizard (`setup`), Profile (`profile`) | `/settings*`, `/users*`, `/auth/roles`, `/suppression*`, `/contacts/import/*`, `/contacts/export` |

### Dashboard
Greeting "Good morning/afternoon/evening, <operator>!". The subtitle says **"Your AI Sales Agent is ready"** only when
`/ai/status` reports the provider available *and* the configured model installed; otherwise "Local AI not available —
human-assisted mode" (or that the model is missing). Four metric cards: Total Contacts (`contacts_total`), Called Today
(`calls_today`, last 24 h), Interested and Conversions (`contacts_by_stage.interested` / `.converted`). **No
"vs last week" deltas are shown** because the API does not return last week's figures. "Calls This Week" draws
`calls_daily` as gold bars. "Connection Rate" is a donut of the last 7 days' outcomes (connected / no answer / busy /
failed / still open) and shows "no calls yet" when `calls_week` is 0. "Live AI Status" lists LLM, STT, TTS and the
number of approved knowledge documents with Ready / Not available chips. Recent Calls, Quick Actions, the "Open Call
Console" dark banner, Device Connection (model, Android version, network, battery, Wi-Fi calling, in-call — taken from
the latest `session.heartbeat` received in this session; "Not paired" otherwise) and a campaign list with status chips.
The "live database" pill means every number is an aggregate of local SQLite rows.

### Contacts / Contact detail / Eligibility
Search, filter chips **All / Not called** (stage `new`) **/ Follow-up** (has `next_followup_at`) **/ Interested / Do
not call** (opted out), stage/consent/sort filters, paging (50 per page), status chips and per-row **Call** (creates a
call job) and **Open** actions. "+ New contact" validates business name and phone (red border + inline message) before
sending; a duplicate phone number asks whether to create anyway. Contact detail: gold initials avatar, **Call**,
**Message (disabled — SELL AGENT has no SMS/WhatsApp feature)**, **Edit**, **More** (eligibility, follow-up, consent,
archive, opt-out), lead-stage dropdown, tabs Details / Call History / Notes / Permissions / Eligibility / Follow-ups.
The Eligibility tab shows the backend's verdict with every blocking reason, warning and check (quiet hours, rate,
attempts, consent, suppression, campaign status, route capability).

### Call Console
Left: open calls and queued jobs. Centre: avatar, name, number, a **state chip with the real `conversation_state`**,
the mode chip **"Human-assisted: operator speaks"**, a call timer (from `connected_at`/`started_at`), the agent line
to read aloud, its source (`script` / `llm`), guardrail result and language, the prospect-utterance box (Enter sends to
`/calls/{id}/step`), language selector auto/हिन्दी/English and controls **Connected / No answer / Busy**, **Mute** and
**Keypad** (disabled: "available on the paired phone"), **Record outcome…** (with optional follow-up) and the red
**End call / cancel**. Right: Transcript, AI notes (knowledge refs, guardrail JSON, LLM latency, call notes) and Device
events (`call.state` events from the paired phone via the WebSocket). The label "AI Speaking" is never shown in this
release because autonomous mode is release-gated. Call queue tab: create jobs (manual or android_companion route),
queue (re-checks eligibility), dispatch, cancel, view the stored eligibility result of blocked jobs, and the route
capability badges including **"autonomous: NOT SUPPORTED (release gate closed)"**. Call history: paged list, detail
dialog with transcript, events and notes.

### Other screens
* **Campaigns** – create/edit (autonomous option disabled while the gate is closed), status transitions offered only
  where the backend allows them, add contacts from the CRM (multi-select), membership and outcome statistics.
* **Follow-ups** – grouped by day; red = overdue, amber = due today, gold = upcoming, green = done.
* **Reports** – stage and outcome tables, calls per day, per-campaign job/outcome breakdown, CSV export of the full call
  history (UTF-8 with BOM for Excel).
* **Knowledge Base** – filter by status (`pending_review`, approved, rejected, superseded, expired) and category,
  create, import .txt/.md/.csv (imported as untrusted, pending review), injection flags shown in red; approving a
  flagged document needs the acknowledgement checkbox; reject with reason; new version (supersede); retrieval test.
* **AI Settings** – model manager (provider status, installed models, catalog; the pull button needs the
  "I understand this downloads ~X GB" checkbox **and** `privacy.allow_external_network`); diagnostics (chat test with
  latency, conversation **SIMULATION**, TTS playback, **SIMULATED LOOPBACK**, AI run log); sales script editor (see §5).
* **Devices** – pairing window with the code in large gold digits, expiry countdown, LAN addresses/port/TLS
  fingerprint, pending request approve/reject, device list with revoke/delete, LAN listener toggle with a warning.
  Audio feasibility console: the 16-step plan, latest result per step, operator **Confirm** (real-device rows only),
  manual record dialog (`real_device` or `simulated`), release-gate panel with the backend's explanation; results from
  the diagnostic APK appear live (`audio_test.result`).
* **System Status** – `/health` JSON, tail of `backend.log`, versions (desktop, backend, protocol), "Open data folder",
  audit log with action-prefix and severity filters; backups (passphrase when `backup.encrypt` is on), verify, restore
  (warning, typed confirmation **RESTORE**, restart recommended afterwards).
* **Settings** – typed editors for every `/settings` key grouped by prefix; `calling.autonomous_enabled` is disabled
  with an explanatory tooltip while the release gate is closed; warnings before enabling external network, LAN
  pairing, call recording or telemetry; retention run; "Clear emergency stop". Suppression list (add with reason, lift
  with justification, check a number). Import/export (CSV/XLSX upload → column mapping → preview with
  valid/invalid/duplicate counts → duplicate policy → commit; export CSV/XLSX). Setup wizard re-run. **Profile**: the
  local operator ("Local operator — no cloud account"); there is no sign-in, Google/Microsoft login, plan or billing.

### Users, roles and "Switch user"
The desktop always starts as the built-in **owner** (admin) through the local token. Settings › **Users & Roles**
(admin only; the tab is hidden for other roles) creates local users (username `a-z0-9._-`, display name, role
admin / manager / operator / viewer, PIN 6–12 digits that is not repeated or sequential — validated before sending),
edits role/display name, disables/enables, resets PINs and deletes users, and shows the read-only permission matrix
from `/auth/roles`. The header avatar menu (▾) has **Switch user…** (PIN sign-in → `POST /auth/login`; every request
then uses the user's JWT and the desktop WebSocket reconnects with `?token=<jwt>`) and **Return to owner** (logs the
user out and goes back to the local token). The chip next to the name shows `actor · role`.
Actions the current role lacks (from `/auth/whoami` permissions `'<area>:read'` / `'<area>:write'`, `'*'` = all) are
disabled with the tooltip "Your role (<role>) can't do this"; screens the role cannot read show a red notice instead of
data. If the backend still answers 403 the message reads "Your role (<role>) can't do this — …". **EMERGENCY STOP stays
enabled for every role**; clearing it needs `calls:write`.

### Background workers and notifications
System Status › **Workers** lists the call-queue dispatcher, campaign engine, follow-up scheduler and daily report with
runs, errors, items, last run, duration, last error/result and enabled state (`/system/workers`), plus the AI and speech
job queues. **Run now** executes one cycle; **Disable/Enable** pauses a schedule until the backend restarts.
Backend `event` envelopes on the desktop WebSocket (`queue.ready`, `queue.blocked`, `campaign.jobs_created`,
`campaign.completed`, `followup.due`, `followup.created`, `report.ready`, `worker.error`) appear as a notification in
the header/status bar and in the **bell** menu with an unread count; the matching screen (Call queue, Campaigns,
Follow-ups, Reports, Workers) refreshes if it is open.

### Additions per screen
* **Dashboard** – the metric cards show real deltas from `comparisons` ("+12% from last week", "-50% from yesterday",
  "new" / "+N added this week" when the previous period was 0, nothing when both are 0) and a 7-day prospect sentiment
  row (positive / neutral / negative / unknown counts).
* **Campaigns** – gold **▶ Start Campaign** (authorizes if draft, activates, runs the campaign engine once and reports
  how many jobs it created), **Pause**, "Enable follow-up" toggle with "follow-up after N days" (1–60) in create/edit,
  and a progress bar from `stats.progress_percent`.
* **Follow-ups** – List and **Calendar** tabs; the month view (previous / next / today) shows per-day counts with a gold
  dot for open, red for overdue and ✓ for done; clicking a day lists its follow-ups.
* **Reports** – **Daily reports** panel: list of generated days, **Generate now** for a chosen date, **Open** (saved to
  the temp folder and opened with the default app) or **Save as…** for `report.html`, `summary.json`, `calls.csv`.
  Settings keys `reports.daily_enabled` and `reports.daily_at` (HH:MM, validated) control the schedule.
* **Call Console** – each prospect line is tagged and coloured with its sentiment, and an overall **sentiment** chip
  sits next to the state chip. After the outcome is saved a **Call Summary** card shows duration, result, sentiment,
  key points, knowledge used, next action and notes (`/calls/{id}/summary`, built deterministically from the transcript);
  the same summary is the first tab of the Call history detail dialog.
* **Live transcription (PC microphone) – audio is not stored** – off by default. It requires the setting
  `privacy.allow_live_transcription` (warning dialog when enabling), a live call, and the operator ticking "I read the
  disclosure to the prospect" and "The prospect agreed" in a dialog that shows `privacy.recording_disclosure_text`
  (`POST /calls/{id}/transcription-consent`). Audio is captured with `sounddevice` (PortAudio) at 16 kHz mono PCM16 and
  streamed to `/api/v1/ws/transcribe`; a mic chip shows listening / speech / error, final text lines are appended with
  their sentiment, and the speaker can be switched between prospect and operator. If PortAudio or the microphone is
  missing the card says so plainly.
* **AI Settings › diagnostics** – the chat test now streams tokens from `/ai/chat-stream` (SSE) as they arrive, with a
  **Cancel** button (`/system/ai-jobs/{id}/cancel`) and first-token / total latency when done.
* **AI model manager** – models with a `license_warning` (qwen2.5:3b, Qwen Research License, NON-COMMERCIAL) show the
  warning and need a second checkbox ("I confirm I have permission…") before Pull is enabled. Whisper default is `base`.
* **Knowledge Base** – import accepts .txt, .md, .csv, **.pdf and .docx** (15 MB limit checked before upload).
* **Contacts** – new **Category** field (default "Gym / Fitness", editable list) in create/edit/detail and a table column.
* **System Status / setup wizard** – a chip shows "Database: encrypted (AES-256)" when SQLCipher is active, otherwise
  "NOT encrypted — …". Backups always ask for a passphrase when the database is encrypted.

## 4. Emergency stop

The red **EMERGENCY STOP** button (header, every screen) and **Ctrl+Shift+X** act immediately, without a confirmation
dialog: the app sends `safety.emergency_stop` over the desktop WebSocket (lowest latency) and calls
`POST /api/v1/call-jobs/emergency-stop` (authoritative). The backend sets `calling.emergency_stop_active`, cancels all
pending/queued/dispatched/in-progress jobs and forwards the stop to connected phones. The red banner stays until the
stop is cleared under Settings › Privacy & calling settings › **Clear emergency stop** (asks for confirmation).

## 5. Sales script editor

Built-in Hindi/English lines (from `sellagent_ai.conversation.scripts`) are shown read-only next to editable overrides.
Overrides are stored as a knowledge document in category `general` titled **"Sales script overrides"** with structured
JSON `{"scripts": {state: {"hi": …, "en": …}}}`. Saving creates a new version in `pending_review`; it must be approved in
the Knowledge Base. **Digits are rejected** in overrides: prices and other numbers are injected only from approved
pricing facts.

## 6. Keyboard shortcuts

| Keys | Action |
| --- | --- |
| Ctrl+Shift+X | EMERGENCY STOP |
| Ctrl+K | focus the header search |
| header ▾ | Switch user… / Return to owner / Profile |
| Ctrl+1 … Ctrl+9 | first nine sidebar entries (Dashboard … Devices) |
| F5 | refresh the current screen |
| Enter (Call Console utterance box) | send the prospect's words / get the next agent line |
| Enter (search boxes) | search |
| Tab / Shift+Tab | move between controls (all buttons have accessible names) |

## 7. What is labelled MOCK / SIMULATION and why

Anything that is not real phone-call evidence carries an amber `badge-mock` label:

| Label | Where | Why |
| --- | --- | --- |
| **SIMULATION** | AI Settings › diagnostics › Conversation SIMULATION | typed text against a fictional "Demo Gym"; no phone, no audio, no contact record |
| **SIMULATED LOOPBACK** | diagnostics › Speech | Piper → VAD → Whisper on the PC proves the local pipeline, not cellular audio |
| **PC-LOCAL DIAGNOSTIC** / "DIAGNOSTIC / SIMULATION" | model manager, diagnostics header | STT/TTS/LLM checks on this PC say nothing about call audio |
| `[SIMULATED]` kind | Audio feasibility console | `simulated` rows can never be confirmed and never open the release gate |
| `source: llm` badge | Call Console | the line was rephrased by the local model (guardrail result shown); `script` lines are approved text |
| autonomous: NOT SUPPORTED (release gate closed) | Call queue routes | the backend has no operator-confirmed real-device inbound **and** outbound audio PASS |

Nothing in the app shows a fake call status or invented analytics: empty states are shown instead of sample data.

## 8. Building the installer

On Windows 11 with the venv active:

```powershell
python scripts\build_windows.py          # icons + bundled theme + PyInstaller + Inno Setup
# or step by step:
python scripts\build_windows.py --only icons --only theme
python -m PyInstaller --noconfirm --clean scripts\sellagent.spec   # -> dist\SellAgent\ (portable folder)
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=0.1.0 scripts\installer.iss   # -> dist\SellAgent-Setup-0.1.0.exe
```

Inno Setup 6 is free (`winget install JRSoftware.InnoSetup` or `choco install innosetup`). The installer puts the app in
`C:\Program Files\SellAgent`, creates Start-menu and optional desktop shortcuts, and keeps
`%LOCALAPPDATA%\SellAgent` on uninstall unless "Also delete my SELL AGENT data" is ticked (with a second confirmation).
CI (`.github/workflows/build-windows.yml`) runs the unit, integration and UI tests on `windows-latest` and uploads the
installer and the portable folder as artifacts.

### Code signing and SmartScreen

The installer and executables are **unsigned** by default, so Windows SmartScreen shows "Windows protected your PC" on
first run ("More info" → "Run anyway"). Legitimate ways to reduce that:

* **OV (organisation-validated) code-signing certificate** from a public CA (DigiCert, Sectigo, GlobalSign, …). Since
  2023 the private key must live on a hardware token or cloud HSM. SmartScreen reputation still builds up over time.
* **EV code-signing certificate** – stricter validation, also HSM-backed; historically gave immediate reputation, but
  Microsoft no longer guarantees that, so expect some warnings for a new publisher either way.
* **Azure Trusted Signing** (Microsoft's managed signing service, paid monthly subscription) – identity validation by
  Microsoft, keys in Azure, integrates with `signtool`.

Sign with `signtool sign /fd sha256 /tr <timestamp-url> /td sha256 …` for `SellAgent.exe`, `sellagent-backend.exe` and
the setup file (Inno Setup's `SignTool=` directive is prepared in `installer.iss`). A self-signed or "free" certificate
does **not** remove SmartScreen warnings.

## 9. Tests

`tests/ui` (marker `ui`) starts the **real backend as a subprocess** on a free port with a temporary data directory,
builds the `MainWindow` offscreen (`QT_QPA_PLATFORM=offscreen`) and checks: every screen refreshes without error and has
its key widgets; navigation groups cover all screens; the brand QSS is applied verbatim; status chips are honest (Local
AI Offline without a model); the contact dialog validates and creates a contact that appears in the table; filter chips
and global search; a manual call job → dispatch → live console (Connected, script greeting) → outcome → history; the
emergency stop button sets `calling.emergency_stop_active`; script overrides reject digits and save a pending document;
simulated audio rows cannot be confirmed; Profile has no cloud account. `test_features.py` covers the blueprint
features: users/roles (create a viewer through the dialog, PIN sign-in, JWT + WebSocket reconnect, write actions locked,
403 wording, emergency stop still enabled, return to owner), workers run/disable, event envelopes → toast + bell,
campaign start/pause/follow-up fields/progress, follow-up calendar, daily report generate/open/save, dashboard deltas
and sentiment, call sentiment + summary (console and history), the live-transcription gate + consent + streaming with a
synthetic audio source, SSE chat streaming, the qwen2.5 licence gate, PDF/DOCX import filter, contact category and the
database-encryption chip. The tests skip cleanly when PySide6 is missing.

```powershell
$env:QT_QPA_PLATFORM = "offscreen"; python -m pytest tests/ui -q
```

## 10. Not verified on Windows yet

The app was developed and tested headless on Linux. The following need a check on a Windows 11 PC: DPAPI token reading
by the desktop, `CREATE_NO_WINDOW` for the backend child, the PyInstaller build and the frozen backend path, the Inno
Setup uninstall checkbox, Nirmala UI glyph fallback, microphone capture with sounddevice/PortAudio (the container
has no PortAudio, so the transcription test feeds synthetic PCM frames), `winsound` TTS playback (QtMultimedia is not in
PySide6-Essentials, so the app falls back to `winsound`), high-DPI scaling and the "Open data folder" button.
