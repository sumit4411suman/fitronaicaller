"""Pure-helper tests for telecom/adb.py (USB-ADB call control). Headless: no device, no adb binary.

These cover command construction, output parsing, and - importantly - that the audio verdict is honestly
negative and never phrased as a working path. See docs/JIO_DIRECT_CALLING.md."""

from __future__ import annotations

import pytest
from sellagent_backend.telecom.adb import (
    audio_path_verdict,
    call_state_query_args,
    device_facts,
    dial_intent_args,
    end_call_args,
    looks_like_e164,
    parse_call_state,
    parse_dialer_role,
    parse_props,
)


def test_e164_validation():
    assert looks_like_e164("+919876543210")
    assert looks_like_e164("9876543210")
    assert not looks_like_e164("")
    assert not looks_like_e164("+91 98765 43210")  # spaces rejected
    assert not looks_like_e164("tel:123; rm -rf /")  # injection-ish rejected
    assert not looks_like_e164("12")  # too short


def test_dial_intent_args_builds_call_intent():
    args = dial_intent_args("+919876543210")
    assert args == ["shell", "am", "start", "-a", "android.intent.action.CALL", "-d", "tel:+919876543210"]


def test_dial_intent_args_refuses_bad_number():
    with pytest.raises(ValueError, match="implausible number"):
        dial_intent_args("not-a-number")


def test_end_and_state_args():
    assert end_call_args() == ["shell", "input", "keyevent", "6"]
    assert call_state_query_args() == ["shell", "dumpsys", "telephony.registry"]


def test_parse_call_state():
    assert parse_call_state("  mCallState=0  other=1") == "IDLE"
    assert parse_call_state("mCallState = 1") == "RINGING"
    assert parse_call_state("foo mCallState=2 bar") == "IN_CALL"
    assert parse_call_state("no state here") == "unknown"
    assert parse_call_state("") == "unknown"


def test_parse_props_and_device_facts():
    out = "[ro.product.model]: [SM-S931B]\n[ro.soc.model]: [SM8750]\n[garbage line]\n[ro.build.version.release]: [17]\n"
    props = parse_props(out)
    facts = device_facts(props)
    assert facts["model"] == "SM-S931B"
    assert facts["soc_model"] == "SM8750"
    assert facts["android_release"] == "17"
    assert facts["board_platform"] == ""  # absent -> empty, not a crash


def test_parse_dialer_role():
    assert parse_dialer_role("android.app.role.DIALER: com.samsung.android.dialer") == "com.samsung.android.dialer"
    assert parse_dialer_role("com.android.dialer\n") == "com.android.dialer"
    assert parse_dialer_role("") == ""


def test_audio_verdict_is_honestly_negative():
    v = audio_path_verdict()
    # The whole point: USB ADB cannot carry call audio. If either of these ever flips true it must be because a
    # real, supported path was implemented and proven - not because this constant was softened.
    assert v["remote_capture_over_adb"] is False
    assert v["uplink_injection_over_adb"] is False
    assert v["path"] == "none"
    assert "CAPTURE_AUDIO_OUTPUT" in v["reason"]
    assert isinstance(v["supported_alternatives"], list) and v["supported_alternatives"]
