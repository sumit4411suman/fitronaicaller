"""Evidence checker for the real-device audio feasibility run. Marks: device, real-device-tested."""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.device

STEPS = ["pairing", "call_state_reporting", "outgoing_call", "remote_speech_capture", "generated_speech_transmission", "simultaneous_two_way", "route_earpiece", "route_speaker", "route_bluetooth", "route_wired", "latency_echo_quality", "screen_locked", "wifi_interruption", "hindi_phrases", "english_phrases", "jio_wifi_calling", "platform_api_support", "jio_number_retention"]


@pytest.fixture(scope="module")
def api():
    if os.environ.get("SELLAGENT_DEVICE_TESTS") != "1":
        pytest.skip("real-device tests disabled (set SELLAGENT_DEVICE_TESTS=1 on the Windows PC with the phone paired)")
    base = os.environ.get("SELLAGENT_BACKEND_URL", "http://127.0.0.1:8765")
    token = os.environ.get("SELLAGENT_LOCAL_TOKEN")
    if not token:
        from pathlib import Path

        from sellagent_backend.config import get_settings
        from sellagent_backend.security.secret_store import read_secret_file

        token = read_secret_file(Path(get_settings().local_token_path))
    return httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=10)


@pytest.mark.parametrize("step", STEPS)
def test_step_has_confirmed_real_device_evidence(api, step):
    rows = [r for r in api.get("/api/v1/audio-tests").json() if r["step"] == step and r["kind"] == "real_device" and r["operator_confirmed"]]
    if not rows:
        pytest.skip(f"{step}: NOT TESTED on a real device yet")
    latest = rows[0]
    assert latest["phone_model"], "evidence must record the phone model"
    assert latest["status"] in ("pass", "fail", "blocked"), "a confirmed row must carry an observed status"
    if latest["status"] != "pass":
        pytest.fail(f"{step}: real-device result = {latest['status']} ({latest.get('error_message')})")


def test_release_gate_reflects_evidence(api):
    gate = api.get("/api/v1/settings/release-gate").json()
    assert gate["allowed"] == (gate["remote_audio_capture_verified"] and gate["audio_injection_verified"])
