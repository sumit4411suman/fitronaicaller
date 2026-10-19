#!/usr/bin/env python3
"""USB-ADB Jio direct-calling diagnostic for SELL AGENT (run on the Windows 11 PC, phone on a USB cable).

This proves, with real device output and no guessing, exactly what the "Windows -> USB cable -> Galaxy S25 on
Jio" path can and cannot do, split into the separate questions the spec asks:

  --facts     device model / SoC / Android / VoLTE / default-dialer role (read-only getprop + dumpsys)
  --state     read the current coarse call state (IDLE / RINGING / IN_CALL)
  --dial N    place ONE call to N via the standard CALL intent (requires --consent); reads state afterwards
  --endcall   hang up the current call (KEYCODE_ENDCALL) - the Stop/Emergency-Stop primitive
  --audio     report the AUDIO verdict: ADB carries NO live call audio in either direction, and WHY

With no flags it runs --facts, --state and --audio. It writes a JSON evidence file (--out) you can attach to a
report or import into the Audio feasibility console. It NEVER claims two-way AI audio works: a successful dial or
a call-state read is control, not audio. See docs/JIO_DIRECT_CALLING.md.

Nothing here roots the phone, uses a hidden API, or bypasses Android security. It only runs ordinary `adb`
commands: read-only queries plus the same CALL intent and end-call key the Phone app uses.

Prerequisites: Android platform-tools (`adb`) on PATH, USB debugging ON, and "Allow restricted settings" granted
on the S25. Place calls only to a consenting participant on a number you are authorised to dial.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Pure, unit-tested helpers from telecom/adb.py. That module has no internal dependencies (stdlib only), so we
# load the single file directly - this keeps the diagnostic runnable on the PC without the whole backend
# installed, and avoids importing the package __init__ (which pulls sqlalchemy, the protocol package, etc.).
_ROOT = Path(__file__).resolve().parent.parent
_adb_path = _ROOT / "services" / "local-backend" / "sellagent_backend" / "telecom" / "adb.py"
_spec = importlib.util.spec_from_file_location("sellagent_adb_helpers", _adb_path)
if _spec is None or _spec.loader is None:  # pragma: no cover - defensive
    raise SystemExit(f"cannot load adb helpers from {_adb_path}")
_adb_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_adb_mod)
audio_path_verdict = _adb_mod.audio_path_verdict
call_state_query_args = _adb_mod.call_state_query_args
device_facts = _adb_mod.device_facts
dial_intent_args = _adb_mod.dial_intent_args
dialer_role_query_args = _adb_mod.dialer_role_query_args
end_call_args = _adb_mod.end_call_args
looks_like_e164 = _adb_mod.looks_like_e164
parse_call_state = _adb_mod.parse_call_state
parse_dialer_role = _adb_mod.parse_dialer_role
parse_props = _adb_mod.parse_props
props_query_args = _adb_mod.props_query_args


def _adb(exe: str, args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout)  # noqa: S603


def connected(exe: str) -> tuple[bool, str]:
    try:
        devs = _adb(exe, ["devices"], timeout=10)
    except FileNotFoundError:
        return False, "adb not found. Install Android platform-tools and/or pass --adb <path>."
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    lines = [ln for ln in devs.stdout.splitlines()[1:] if ln.strip() and "\tdevice" in ln]
    if not lines:
        return False, f"no authorised device. `adb devices` said:\n{devs.stdout.strip()}"
    return True, lines[0].split("\t")[0]


def facts(exe: str) -> dict:
    out: dict = {}
    props = parse_props(_adb(exe, props_query_args()).stdout)
    out["device"] = device_facts(props)
    reg = _adb(exe, call_state_query_args()).stdout
    out["volte_lines"] = [ln.strip() for ln in reg.splitlines() if "volte" in ln.lower() or "ims" in ln.lower()][:6]
    out["default_dialer"] = parse_dialer_role(_adb(exe, dialer_role_query_args()).stdout)
    return out


def read_state(exe: str) -> str:
    return parse_call_state(_adb(exe, call_state_query_args()).stdout)


def dial(exe: str, number: str, settle: float = 6.0) -> dict:
    if not looks_like_e164(number):
        return {"error": f"implausible number {number!r}; expected E.164 digits, optional leading +"}
    before = read_state(exe)
    res = _adb(exe, dial_intent_args(number))
    time.sleep(settle)
    after = read_state(exe)
    return {
        "number_masked": number[:3] + "…" + number[-3:] if len(number) > 6 else "…",
        "intent_exit_code": res.returncode,
        "intent_stderr": res.stderr.strip()[:300],
        "call_state_before": before,
        "call_state_after": after,
        "dialed": after in ("RINGING", "IN_CALL") or before != after,
        "note": "A connected call is control-plane proof only. It does NOT put call audio on the PC.",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="SELL AGENT USB-ADB Jio direct-calling diagnostic")
    ap.add_argument("--facts", action="store_true", help="device model / SoC / Android / VoLTE / dialer role")
    ap.add_argument("--state", action="store_true", help="read the current coarse call state")
    ap.add_argument("--dial", metavar="E164", help="place ONE call to this number (needs --consent)")
    ap.add_argument("--consent", action="store_true", help="confirm the participant consented and you may dial")
    ap.add_argument("--endcall", action="store_true", help="hang up the current call (KEYCODE_ENDCALL)")
    ap.add_argument("--audio", action="store_true", help="report the honest call-audio verdict for USB ADB")
    ap.add_argument("--adb", dest="adb_path", default="adb", help="path to the adb binary")
    ap.add_argument("--out", default=None, help="write the evidence JSON here")
    a = ap.parse_args()

    exe = shutil.which(a.adb_path) or a.adb_path
    report: dict = {
        "tool": "adb_jio_diagnostic",
        "generated_at": datetime.now(UTC).isoformat(),
        "label": "REAL-DEVICE USB-ADB DIAGNOSTIC (operator-run). Control != audio; a dial is not audio evidence.",
        "adb": exe,
    }
    ok, ident = connected(exe)
    report["connected"] = ok
    report["device_serial" if ok else "connect_error"] = ident

    default_run = not (a.facts or a.state or a.dial or a.endcall or a.audio)
    if ok and (a.facts or default_run):
        report["facts"] = facts(exe)
    if ok and (a.state or default_run):
        report["call_state"] = read_state(exe)
    if a.dial:
        if not ok:
            report["dial"] = {"error": "no device connected"}
        elif not a.consent:
            report["dial"] = {"error": "refused: pass --consent to confirm the participant agreed to this call"}
        else:
            report["dial"] = dial(exe, a.dial.strip())
    if ok and a.endcall:
        r = _adb(exe, end_call_args())
        report["endcall"] = {"exit_code": r.returncode, "state_after": read_state(exe)}
    if a.audio or default_run:
        report["audio_verdict"] = audio_path_verdict()

    text = json.dumps(report, indent=2)
    print(text)
    if a.out:
        Path(a.out).write_text(text)
        print(f"\nWrote evidence to {a.out}")

    # Always end on the honest headline so output can't be mistaken for an audio pass.
    print(
        "\nUSB ADB can dial, read coarse call state, and hang up on this phone. It canNOT capture the remote "
        "party's voice or inject Priya's voice into the call - ADB exposes no call-audio stream on a non-rooted "
        "S25. Two-way AI audio stays blocked until a supported audio path is proven. See "
        "docs/JIO_DIRECT_CALLING.md.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
