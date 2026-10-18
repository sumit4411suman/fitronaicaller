# Known limitations and compatibility matrix

## Hard limitations (by design or by platform)
1. **No two-way cellular AI audio through an ordinary Android app.** Public APIs do not expose call downlink audio to
   third-party apps (CAPTURE_AUDIO_OUTPUT is privileged) and there is no API to inject audio into the uplink. The only
   path available to a normal app is acoustic (loudspeaker to handset mic). Autonomous mode therefore stays disabled by the
   release gate until real-device evidence says otherwise. Details: `docs/TELECOM_FEASIBILITY.md`.
2. **A consumer Jio SIM is not an authorised channel for automated promotional calling** under TRAI TCCCPR; promotional
   calls require registered telemarketer routes (140 series). Human-assisted calls to consented contacts are the
   supported workflow. Details: `docs/COMPLIANCE_INDIA.md`.
3. **Not benchmarked on target hardware in this release.** LLM/STT/TTS latency, RAM and Hindi quality must be measured
   with `sellagent_ai.benchmark` and `scripts/offline_check.py` on the 16 GB CPU-only PC.
4. **Android apps were not compiled or run on a device in this session** (no Android SDK or phone available). CI builds
   the debug APKs; the Galaxy S25 procedure is in `docs/ANDROID_APPS.md`.
5. **Windows installer not produced here**; `scripts/build_windows.py` and the Windows CI job build it.
6. Knowledge import supports `.txt/.md/.csv`; convert PDF/DOCX to text first.
7. Speech recognition in the live console is operator-driven (type or upload WAV); there is no automatic capture of the
   remote party because of limitation 1.
8. Piper 1.8.0 is GPL-3.0; the default bundle does not include it (see `models/README.md`).
9. Hindi TTS voices exist for Piper but their quality is unverified; English voices are mature.

## Compatibility matrix

| Component | Supported | Notes |
| --- | --- | --- |
| Windows 11 x64, Python 3.12.x | yes (target) | pinned in `requirements*.txt` |
| Windows 10 | untested | should work; DPAPI and Nirmala UI present |
| Linux (dev/CI) | backend, engines, tests, offscreen UI | PortAudio needed for `sounddevice` |
| macOS | untested | not a target |
| Samsung Galaxy S25 (Android 15 / One UI 7+) | target for both apps | minSdk 29, compileSdk 35 |
| Other Android 10+ phones | likely for pairing/call state; audio behaviour differs | not tested |
| Jio SIM with Wi-Fi Calling | call routing unchanged for the app; VoWiFi detection via `Call.Details.PROPERTY_WIFI` when default dialer | `isWifiCallingAvailable` is hidden API, not used |
| Ollama (Windows) | yes | localhost 11434 |
| llama.cpp `llama-server` | yes | OpenAI-compatible endpoint on 8080 |
| faster-whisper 1.2.1 / CTranslate2 4.8.3 | CPU int8 | models tiny..medium |
| Piper 1.8.0 | yes (optional extra) | GPL note |
| SQLite >= 3.35 with FTS5 | required | CPython 3.12 on Windows ships 3.4x with FTS5 |
