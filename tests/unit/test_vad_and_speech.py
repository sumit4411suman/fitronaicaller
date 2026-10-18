import numpy as np
import pytest

from sellagent_speech import EnergyVAD, FasterWhisperSTT, PiperTTS, VadConfig
from sellagent_speech.audio_io import resample
from sellagent_speech.diagnostics import synthetic_vad_selftest

pytestmark = pytest.mark.automated


def test_vad_selftest():
    r = synthetic_vad_selftest()
    assert r["ok"] and r["kind"] == "automated_synthetic"


def test_streaming_vad_onset():
    vad = EnergyVAD(VadConfig(frame_ms=30, min_speech_ms=60))
    frame = int(16000 * 0.03)
    onsets = [vad.feed(np.zeros(frame, dtype=np.float32)) for _ in range(5)]
    onsets += [vad.feed((0.3 * np.sin(np.linspace(0, 50, frame))).astype(np.float32)) for _ in range(5)]
    assert sum(onsets) == 1


def test_resample_length():
    assert len(resample(np.zeros(22050, dtype=np.float32), 22050, 16000)) == 16000


def test_speech_engines_report_unavailable_without_optional_deps(tmp_path):
    ok, msg = FasterWhisperSTT("small", models_dir=tmp_path).available()
    ok2, msg2 = PiperTTS(tmp_path).available()
    # Either installed (then message says so) or clearly unavailable - never a silent failure.
    assert isinstance(ok, bool) and msg and isinstance(ok2, bool) and msg2
