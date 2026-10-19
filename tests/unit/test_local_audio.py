"""Pure helpers for the Bluetooth / local-audio bridge (telecom/local_audio.py). Headless: no audio hardware,
no sounddevice. Covers device classification (phone/HFP detection) and the honest capture-evidence summary."""

from __future__ import annotations

import numpy as np
from sellagent_backend.telecom.local_audio import capture_evidence, classify_devices

DEVICES = [
    {"index": 0, "name": "Microphone (Realtek)", "max_input_channels": 2, "max_output_channels": 0},
    {"index": 1, "name": "Speakers (Realtek)", "max_input_channels": 0, "max_output_channels": 2},
    {"index": 2, "name": "Headset (Galaxy S25 Hands-Free AG Audio)", "max_input_channels": 1, "max_output_channels": 1},
]


def test_classify_flags_phone_hfp_channel():
    c = classify_devices(DEVICES)
    assert len(c["inputs"]) == 2 and len(c["outputs"]) == 2
    assert len(c["hfp_candidates"]) == 1
    hfp = c["hfp_candidates"][0]
    assert hfp["input"] and hfp["output"]
    assert c["has_hfp_capture"] and c["has_hfp_playback"]


def test_classify_no_phone_device():
    c = classify_devices(DEVICES[:2])  # just mic + speakers
    assert c["hfp_candidates"] == []
    assert not c["has_hfp_capture"] and not c["has_hfp_playback"]


def test_capture_evidence_detects_signal_vs_silence():
    sr = 16000
    tone = (0.2 * np.sin(2 * np.pi * 220 * np.linspace(0, 1, sr))).astype(np.float32)
    ev = capture_evidence(tone, sr, label="t")
    assert ev["has_signal"] and ev["rms"] > 0.002 and ev["duration_s"] == 1.0

    silence = np.zeros(sr, dtype=np.float32)
    ev2 = capture_evidence(silence, sr)
    assert not ev2["has_signal"] and "no usable signal" in ev2["note"]

    empty = capture_evidence(np.zeros(0, dtype=np.float32), sr)
    assert not empty["has_signal"] and empty["duration_s"] == 0.0


def test_capture_evidence_is_honest_about_meaning():
    # A strong signal must NOT be phrased as proof of real call audio.
    sr = 16000
    loud = (0.5 * np.sin(2 * np.pi * 300 * np.linspace(0, 1, sr))).astype(np.float32)
    ev = capture_evidence(loud, sr)
    assert ev["has_signal"] and "NOT proof" in ev["note"]
