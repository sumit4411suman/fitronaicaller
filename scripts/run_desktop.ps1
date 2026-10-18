# Launch SELL AGENT desktop from a source checkout on Windows 11 (PowerShell).
#   .\scripts\run_desktop.ps1            -> starts the backend child process + desktop app
#   .\scripts\run_desktop.ps1 -BackendUrl http://127.0.0.1:8765   -> attach to an already running backend
param(
    [string]$BackendUrl = "",
    [switch]$NoWizard
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (Test-Path ".venv\Scripts\python.exe") { $py = ".venv\Scripts\python.exe" } else { $py = "python" }
$env:PYTHONPATH = "services\local-backend;services\ai-engine;services\speech-engine;services\knowledge-base;packages\shared-protocol;apps\windows-desktop"
if ($BackendUrl -ne "") { $env:SELLAGENT_BACKEND_URL = $BackendUrl }
$args = @("-m", "sellagent_desktop.main")
if ($NoWizard) { $args += "--no-wizard" }
& $py @args
exit $LASTEXITCODE
