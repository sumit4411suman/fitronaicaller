"""USB-ADB call-control helpers for the Samsung Galaxy S25 (no paid telephony provider).

This module is the supported-API layer behind the Jio direct-calling path the user asked for: control the
phone over a USB cable with `adb`, nothing more. It can build the commands to place a call, read call state,
and end a call, and it parses the phone's own output into honest facts. It deliberately does NOT try to capture
or inject the live cellular call's audio, because ADB exposes no such stream on a non-rooted phone - see
`audio_path_verdict()` and docs/JIO_DIRECT_CALLING.md for exactly why.

Everything here is pure (string in, value out): the functions build argument lists and parse text, so they are
unit-tested headless with no device and no `adb` binary. The actual subprocess calls live in
scripts/adb_jio_diagnostic.py, which the operator runs on the Windows PC with the phone plugged in.

Security / scope: read-only device queries plus two well-known user actions (CALL intent, end-call keyevent).
No root, no hidden APIs, no accessibility abuse, no system-partition changes.
"""

from __future__ import annotations

import re

# Android TelephonyManager.CALL_STATE_* values as reported by `dumpsys telephony.registry` (mCallState=).
CALL_STATES = {"0": "IDLE", "1": "RINGING", "2": "IN_CALL"}
KEYCODE_ENDCALL = "6"

_E164 = re.compile(r"^\+?[1-9]\d{6,14}$")
_PROP_LINE = re.compile(r"^\[([^\]]+)\]:\s*\[([^\]]*)\]\s*$")
_CALL_STATE = re.compile(r"mCallState\s*=\s*(\d)")
_ROLE_HOLDER = re.compile(r"android\.app\.role\.DIALER.*?:\s*(\S+)", re.IGNORECASE | re.DOTALL)


def looks_like_e164(number: str) -> bool:
    """True for a plausible phone number (optional +, 7-15 digits, no separators). A gate for --dial so the
    diagnostic never shells out `tel:` with operator typos or injected text."""
    return bool(_E164.match((number or "").strip()))


def dial_intent_args(number: str) -> list[str]:
    """`adb shell` args to place a call to `number` via the standard CALL intent.

    This is the ordinary Android "dial this number" action; from the adb shell it reaches TelecomManager the
    same way the Phone app does. Raises on an implausible number so a bad value can never be interpolated into
    the intent. It does NOT bypass anything: the SIM, VoLTE and carrier place the call exactly as a manual dial.
    """
    n = number.strip()
    if not looks_like_e164(n):
        raise ValueError(f"refusing to dial implausible number: {number!r}")
    return ["shell", "am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{n}"]


def end_call_args() -> list[str]:
    """`adb shell` args to hang up the current call (KEYCODE_ENDCALL). Used for cancel / emergency stop."""
    return ["shell", "input", "keyevent", KEYCODE_ENDCALL]


def call_state_query_args() -> list[str]:
    """`adb shell` args to dump the telephony registry so `parse_call_state` can read the coarse call state."""
    return ["shell", "dumpsys", "telephony.registry"]


def props_query_args() -> list[str]:
    """`adb shell` args to read all system properties (model, SoC, Android version) for the device-facts report."""
    return ["shell", "getprop"]


def dialer_role_query_args() -> list[str]:
    """`adb shell` args to read which app holds the default-dialer role."""
    return ["shell", "cmd", "role", "get-role-holders", "android.app.role.DIALER"]


def parse_call_state(dumpsys_output: str) -> str:
    """Map `dumpsys telephony.registry` output to IDLE / RINGING / IN_CALL / unknown. Coarse by design: ADB
    gives no finer, carrier-accurate call lifecycle - that is the companion app's InCallService job."""
    m = _CALL_STATE.search(dumpsys_output or "")
    return CALL_STATES.get(m.group(1), "unknown") if m else "unknown"


def parse_props(getprop_output: str) -> dict[str, str]:
    """Parse `getprop` '[key]: [value]' lines into a dict. Tolerant of blank/garbled lines."""
    props: dict[str, str] = {}
    for line in (getprop_output or "").splitlines():
        m = _PROP_LINE.match(line.strip())
        if m:
            props[m.group(1)] = m.group(2)
    return props


def device_facts(props: dict[str, str]) -> dict[str, str]:
    """Pick the few properties that identify the phone for the evidence file."""
    return {
        "model": props.get("ro.product.model", ""),
        "board_platform": props.get("ro.board.platform", ""),
        "soc_model": props.get("ro.soc.model", ""),
        "android_release": props.get("ro.build.version.release", ""),
        "manufacturer": props.get("ro.product.manufacturer", ""),
    }


def parse_dialer_role(output: str) -> str:
    """Return the package holding the default-dialer role, or '' if none/parse-miss."""
    m = _ROLE_HOLDER.search(output or "")
    if m:
        return m.group(1).strip().strip(".")
    # Newer `cmd role` prints just the package on its own line.
    lines = [ln.strip() for ln in (output or "").splitlines() if ln.strip()]
    return lines[-1] if len(lines) == 1 and "." in lines[-1] else ""


def audio_path_verdict() -> dict[str, object]:
    """The honest, constant verdict on call AUDIO over USB ADB. This never probes "and maybe it works": it
    states the supported-API reality so the diagnostic cannot be mistaken for proof of a working audio path.

    ADB can drive the phone (dial, state, hang up) but exposes no stream of the live cellular/IMS call's audio
    in either direction. Capturing the remote party (VOICE_DOWNLINK / VOICE_CALL) needs CAPTURE_AUDIO_OUTPUT,
    a signature|privileged permission; injecting into the uplink has no public API at all. scrcpy's audio
    forwarding (Android 11+) cannot capture voice-call audio for the same reason. None of this is unlocked by
    more permissions, and rooting the S25 is out of scope (One UI 8 blocks bootloader unlock).
    """
    return {
        "remote_capture_over_adb": False,
        "uplink_injection_over_adb": False,
        "path": "none",
        "reason": (
            "ADB exposes no voice-call audio stream. Capturing the remote party needs CAPTURE_AUDIO_OUTPUT "
            "(signature|privileged); uplink injection has no public API; scrcpy audio forwarding cannot capture "
            "call audio. A non-rooted Galaxy S25 cannot grant these."
        ),
        "supported_alternatives": [
            "Bluetooth HFP (PC as hands-free unit) - works on some PCs; user prefers to avoid Bluetooth.",
            "Wired analog headset path (USB-C DAC + TRRS splitter into a PC line-in) - needs hardware + approval.",
        ],
    }
