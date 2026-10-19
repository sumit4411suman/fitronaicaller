"""Launch the supervised "Run Priya over Bluetooth" tool from the desktop app.

This does NOT place autonomous calls and never bypasses the release gate. It starts
``scripts/run_priya_bluetooth.py`` - the same supervised, one-consenting-participant runner documented in
docs/JIO_DIRECT_CALLING.md and docs/BLUETOOTH_AUDIO.md - in a visible console so the operator can watch Priya,
hear the call, and press Ctrl-C for an emergency stop. The runner itself still requires ``--consent`` and
discloses that Priya is an AI; the desktop confirmation is an extra operator acknowledgement, not a replacement
for it.

The command-building and launchability logic here is pure and unit-tested; the actual process spawn is only used
on a real PC.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from sellagent_desktop import paths

SCRIPT_NAME = "run_priya_bluetooth.py"


def script_path() -> Path | None:
    """Path to the supervised runner next to the app (source checkout), or None if it is not present (e.g. a
    packaged build that does not ship the script)."""
    p = paths.app_root() / "scripts" / SCRIPT_NAME
    return p if p.exists() else None


def build_command(python: str, script: str | Path, *, contact: str = "", business: str = "",
                  match: str = "HF Audio", input_sel: str | None = None, output_sel: str | None = None) -> list[str]:
    """Build the argv for the runner. Bluetooth by default (one hands-free device via --match); pass input_sel
    and output_sel for the wired two-device bridge. Always includes --consent (the runner refuses without it)."""
    cmd = [python, str(script), "--consent"]
    if input_sel or output_sel:
        if input_sel:
            cmd += ["--input", input_sel]
        if output_sel:
            cmd += ["--output", output_sel]
    elif match:
        cmd += ["--match", match]
    if contact:
        cmd += ["--contact", contact]
    if business:
        cmd += ["--business", business]
    return cmd


def display_command(cmd: list[str]) -> str:
    """A copy-pasteable one-line form of the command for the dialog."""
    if sys.platform == "win32":
        return subprocess.list2cmdline(cmd)
    import shlex

    return shlex.join(cmd)


def launchable() -> tuple[bool, str]:
    """Whether the desktop can spawn the runner here. False (with a reason) in a packaged build or when the
    script is absent - the UI then shows the exact command to run by hand instead of failing silently."""
    if paths.is_frozen():
        return False, "This packaged build does not include the Bluetooth runner. Run the command below from your SELL AGENT scripts folder."
    if script_path() is None:
        return False, f"{SCRIPT_NAME} was not found next to the app. Run the command below from your SELL AGENT scripts folder."
    return True, ""


def launch(cmd: list[str]) -> tuple[bool, str]:
    """Spawn the runner in a NEW, VISIBLE console (Windows) so the operator can watch Priya and press Ctrl-C.
    Returns (ok, detail). Never raises into the GUI."""
    try:
        creation = 0
        if sys.platform == "win32":
            creation = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen(cmd, creationflags=creation, cwd=str(paths.app_root()))  # noqa: S603
        return True, "Priya is starting in a new console window. Watch it for the live call; press Ctrl-C there to stop."
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not start the runner: {exc}"
