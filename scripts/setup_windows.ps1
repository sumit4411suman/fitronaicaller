# SELL AGENT - Windows 11 developer/operator setup (run in PowerShell from the repo root)
# 1) Python 3.12.x from python.org (tick "Add to PATH"). 2) Optional: Ollama for Windows. 3) This script.
$ErrorActionPreference = "Stop"
$py = (Get-Command py -ErrorAction SilentlyContinue) ? "py -3.12" : "python"
Write-Host "Creating virtual environment (.venv) with $py"
Invoke-Expression "$py -m venv .venv"
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if ($args -contains "--speech") { .\.venv\Scripts\python.exe -m pip install -r requirements-speech.txt }
.\.venv\Scripts\python.exe -m pip install psutil keyring
Write-Host "`nRunning the automated test suite..."
$env:PYTHONPATH = "services\local-backend;services\ai-engine;services\speech-engine;services\knowledge-base;packages\shared-protocol;apps\windows-desktop"
.\.venv\Scripts\python.exe -m pytest tests\unit tests\integration tests\e2e -q
Write-Host "`nSetup complete. Launch with: .\scripts\run_desktop.ps1   (backend only: .\scripts\run_backend.ps1)"
