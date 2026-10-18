# Setup on Windows 11 (16 GB RAM, CPU only)

## Requirements
* Windows 11 x64, 16 GB RAM, ~6 GB free disk for app + default models.
* Python 3.12.x from python.org ("Add python.exe to PATH").
* Optional: [Ollama for Windows](https://ollama.com/download/windows) for the local LLM.
* Optional: Android Studio (to build the APKs) or download the APKs from the GitHub Actions artifacts.

## Install
```powershell
git clone <repo> ; cd -futuremillionaire
.\scripts\setup_windows.ps1 --speech     # omit --speech to skip whisper/piper
```
The script creates `.venv`, installs the pinned requirements and runs the automated tests. All must pass before you continue.

## First run
```powershell
.\scripts\run_desktop.ps1
```
The desktop app starts the backend on `127.0.0.1:8765`, creates `%LOCALAPPDATA%\SellAgent` (database, logs, backups,
models, local token, LAN certificate) and shows the setup wizard. Backend only: `.\scripts\run_backend.ps1`.

## Local AI models (internet needed for this step only)
```powershell
.\.venv\Scripts\python scripts\download_models.py --list
.\.venv\Scripts\python scripts\download_models.py --llm qwen3:1.7b qwen3:4b --whisper small --piper en_US-lessac-medium --yes
```
Then in **Settings** choose `ai.llm_model`, `ai.whisper_model`, `ai.piper_voice_en` (and a Hindi voice if you installed one).

## Benchmark and offline proof
```powershell
.\.venv\Scripts\python -m sellagent_ai.benchmark --models qwen3:1.7b qwen3:4b --runs 3 --out docs\benchmarks\llm.json
# turn Wi-Fi/Ethernet off, then
.\.venv\Scripts\python scripts\offline_check.py
```
Paste both outputs into `docs/TEST_REPORT.md` under "Target-hardware results".

## Pair the Galaxy S25
1. Settings -> Network -> enable "LAN pairing listener" (warning explains the exposure: port 8766, device routes only, TLS).
2. Devices -> **Open pairing window**: note the code, the PC address and the certificate fingerprint.
3. On the phone (companion or audio-test app) enter address, port, code and fingerprint, then approve the request on the PC.
4. Disable the LAN listener when you are done pairing if you do not need live device events.

## Build the installer (Windows only)
```powershell
.\.venv\Scripts\python scripts\build_windows.py      # PyInstaller + Inno Setup -> dist\SellAgent-Setup-<version>.exe
```
CI does the same on `windows-latest` (`.github/workflows/build-windows.yml`). The installer is unsigned unless you add a
code-signing certificate; see `docs/SECURITY_PRIVACY.md`.
