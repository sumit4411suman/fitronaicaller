@echo off
REM Run Priya over Bluetooth - Windows one-click launcher.
REM First time: double-check your setup with the selftest (no phone needed):
REM     run_priya_bluetooth.bat selftest
REM Real consented test call (be in a live call with audio routed to the PC first):
REM     run_priya_bluetooth.bat call "Rahul" "Power Gym"
setlocal
cd /d "%~dp0\.."
if "%1"=="selftest" (
  python scripts\run_priya_bluetooth.py --selftest
  goto :eof
)
if "%1"=="devices" (
  python scripts\run_priya_bluetooth.py --list-devices
  goto :eof
)
if "%1"=="call" (
  python scripts\run_priya_bluetooth.py --consent --contact "%~2" --business "%~3"
  goto :eof
)
echo Usage:
echo   run_priya_bluetooth.bat selftest            - check setup, no phone
echo   run_priya_bluetooth.bat devices             - list audio devices
echo   run_priya_bluetooth.bat call "Name" "Gym"   - run Priya on the live, consented call
