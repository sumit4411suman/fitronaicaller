#!/usr/bin/env python3
"""Bluetooth / local-audio two-way diagnostic for SELL AGENT (run on the Windows 11 PC).

It answers, with real evidence and no guessing, whether the "Galaxy S25 call <-> Bluetooth HFP <-> Windows audio
<-> local AI" path can actually work on this machine:

  1. lists the PC's audio devices and flags any that look like a phone / Bluetooth hands-free call channel;
  2. checks ADB connectivity to the phone and reads the current call state;
  3. records a few seconds from a chosen input device and reports honest signal numbers.

It writes everything to a JSON evidence file. It NEVER concludes "working" on its own: capturing signal on a
device is not proof it is the remote party's call audio - a human confirms that against the live call. See
docs/BLUETOOTH_AUDIO.md. Nothing here roots the phone or changes Android security.

Usage (on the PC, phone on a real consented test call):
    python bt_audio_diagnostic.py --list
    python bt_audio_diagnostic.py --capture --input "Hands-Free" --seconds 5 --out evidence.json
    python bt_audio_diagnostic.py --adb                 # check phone control + call state
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Import the pure, tested helpers from the backend package. Add its path if run standalone.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "services" / "local-backend"))
from sellagent_backend.telecom.local_audio import capture_evidence, classify_devices  # noqa: E402


def list_devices() -> dict:
    try:
        import sounddevice as sd
    except Exception as exc:  # noqa: BLE001
        return {"error": f"sounddevice not installed: {exc}. Run: pip install sounddevice"}
    try:
        apis = sd.query_hostapis()
    except Exception:  # noqa: BLE001
        apis = []
    devices = []
    for i, d in enumerate(sd.query_devices()):
        api = apis[d.get("hostapi", 0)]["name"] if d.get("hostapi", 0) < len(apis) else "?"
        devices.append({"index": i, "name": d["name"], "host_api": api, "max_input_channels": d["max_input_channels"], "max_output_channels": d["max_output_channels"]})
    return {"devices": devices, "classified": classify_devices(devices)}


def check_adb(adb: str = "adb") -> dict:
    exe = shutil.which(adb) or adb
    out: dict = {"adb": exe}
    try:
        devs = subprocess.run([exe, "devices"], capture_output=True, text=True, timeout=10)  # noqa: S603
        out["devices_raw"] = devs.stdout.strip()
        lines = [ln for ln in devs.stdout.splitlines()[1:] if ln.strip() and "device" in ln]
        out["connected"] = len(lines)
        if lines:
            state = subprocess.run([exe, "shell", "dumpsys", "telephony.registry"], capture_output=True, text=True, timeout=10)  # noqa: S603
            import re

            m = re.search(r"mCallState\s*=\s*(\d)", state.stdout)
            out["call_state"] = {"0": "IDLE", "1": "RINGING", "2": "IN_CALL"}.get(m.group(1) if m else "", "unknown")
    except FileNotFoundError:
        out["error"] = "adb not found. Install Android platform-tools and/or pass --adb <path>."
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    return out


def capture(input_device: str | int | None, seconds: float) -> dict:
    try:
        import numpy as np
        import sounddevice as sd
    except Exception as exc:  # noqa: BLE001
        return {"error": f"sounddevice/numpy not installed: {exc}"}
    try:
        info = sd.query_devices(input_device, "input") if input_device not in (None, "") else sd.query_devices(kind="input")
        rate = int(info["default_samplerate"])
        frames = int(rate * seconds)
        rec = sd.rec(frames, samplerate=rate, channels=1, dtype="float32", device=input_device)
        sd.wait()
        return capture_evidence(np.asarray(rec).reshape(-1), rate, label=f"input={input_device!r}")
    except Exception as exc:  # noqa: BLE001
        return {"error": f"capture failed: {exc}", "device": str(input_device)}


def main() -> None:
    ap = argparse.ArgumentParser(description="SELL AGENT Bluetooth / local-audio two-way diagnostic")
    ap.add_argument("--list", action="store_true", help="list audio devices and flag phone/HFP candidates")
    ap.add_argument("--adb", dest="do_adb", action="store_true", help="check ADB phone control and call state")
    ap.add_argument("--adb-path", default="adb")
    ap.add_argument("--capture", action="store_true", help="record from an input device and report signal")
    ap.add_argument("--input", default=None, help="input device name substring or index")
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--out", default=None, help="write the evidence JSON here")
    a = ap.parse_args()

    report: dict = {"tool": "bt_audio_diagnostic", "generated_at": datetime.now(UTC).isoformat(), "label": "REAL-DEVICE DIAGNOSTIC (operator-run); signal on a device is NOT proof of live call audio"}
    if a.list or not (a.list or a.do_adb or a.capture):
        report["audio"] = list_devices()
    if a.do_adb:
        report["adb"] = check_adb(a.adb_path)
    if a.capture:
        report["capture"] = capture(a.input, a.seconds)

    text = json.dumps(report, indent=2)
    print(text)
    if a.out:
        Path(a.out).write_text(text)
        print(f"\nWrote evidence to {a.out}")
    # Honest guidance, never an automatic pass.
    cls = report.get("audio", {}).get("classified") if isinstance(report.get("audio"), dict) else None
    if cls is not None and not (cls["has_hfp_capture"] and cls["has_hfp_playback"]):
        print("\nNOTE: no Windows device looks like a two-way phone/Bluetooth call channel. On standard Windows the "
              "PC cannot act as the phone's Bluetooth hands-free unit, so the all-wireless path usually has no "
              "device to open. See docs/BLUETOOTH_AUDIO.md for the alternatives.", file=sys.stderr)


if __name__ == "__main__":
    main()
