"""Tests for the desktop's supervised Priya-over-Bluetooth launcher (sellagent_desktop.priya_launcher).

Pure command-building and launchability logic - no Qt, no real process spawned."""

from __future__ import annotations

from sellagent_desktop import priya_launcher as pl


def test_build_command_bluetooth_default():
    cmd = pl.build_command("python", "run.py", contact="Rahul", business="Power Gym")
    assert cmd == ["python", "run.py", "--consent", "--match", "HF Audio", "--contact", "Rahul", "--business", "Power Gym"]


def test_build_command_always_has_consent():
    # The runner refuses without --consent; the GUI must never build a command that omits it.
    assert "--consent" in pl.build_command("python", "run.py")


def test_build_command_wired_two_devices():
    cmd = pl.build_command("python", "run.py", input_sel="Line In", output_sel="USB-C DAC")
    assert "--input" in cmd and "Line In" in cmd and "--output" in cmd and "USB-C DAC" in cmd
    assert "--match" not in cmd  # wired overrides the single-device Bluetooth match


def test_display_command_is_one_line():
    line = pl.display_command(["python", "run.py", "--contact", "Power Gym"])
    assert "run.py" in line and "\n" not in line


def test_script_path_found_in_source_checkout():
    # In the repo (not frozen) the runner script exists next to the app root.
    p = pl.script_path()
    assert p is not None and p.name == "run_priya_bluetooth.py"


def test_launchable_in_dev():
    ok, why = pl.launchable()
    assert ok and why == ""
