"""Optional PC audio I/O via sounddevice (used for local diagnostics only - NOT for cellular call audio)."""

from __future__ import annotations

import numpy as np


def devices() -> list[dict]:
    try:
        import sounddevice as sd
    except (ImportError, OSError):
        return []
    return [{"index": i, "name": d["name"], "inputs": d["max_input_channels"], "outputs": d["max_output_channels"], "default_samplerate": d["default_samplerate"]} for i, d in enumerate(sd.query_devices())]


def play(audio: np.ndarray, sample_rate: int) -> None:
    import sounddevice as sd

    sd.play(audio, sample_rate)
    sd.wait()


def record(seconds: float, sample_rate: int = 16000) -> np.ndarray:
    import sounddevice as sd

    data = sd.rec(int(seconds * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    return data[:, 0]


def resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate:
        return audio.astype(np.float32)
    n = int(len(audio) * dst_rate / src_rate)
    x_old = np.linspace(0, 1, num=len(audio), endpoint=False)
    x_new = np.linspace(0, 1, num=n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)
