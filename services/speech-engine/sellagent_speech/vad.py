"""Energy-based voice activity detection with hangover. Pure numpy; works offline on CPU.
Optional: if ``webrtcvad`` is installed it is used for frame decisions instead."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class VadConfig:
    sample_rate: int = 16000
    frame_ms: int = 30
    energy_threshold_db: float = -40.0  # dBFS
    min_speech_ms: int = 200
    hangover_ms: int = 300


@dataclass
class Segment:
    start_s: float
    end_s: float


def dbfs(frame: np.ndarray) -> float:
    if frame.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(frame.astype(np.float64)))))
    return 20 * np.log10(max(rms, 1e-9))


class EnergyVAD:
    name = "energy"

    def __init__(self, cfg: VadConfig | None = None) -> None:
        self.cfg = cfg or VadConfig()
        self._frame = int(self.cfg.sample_rate * self.cfg.frame_ms / 1000)
        self._speech_frames = 0
        self._silence_frames = 0
        self.in_speech = False
        self.barge_in = False

    def is_speech_frame(self, frame: np.ndarray) -> bool:
        return dbfs(frame) > self.cfg.energy_threshold_db

    def process(self, audio: np.ndarray) -> list[Segment]:
        """Batch: return speech segments (seconds) for float32 mono audio in [-1, 1]."""
        f = self._frame
        n = len(audio) // f
        flags = [self.is_speech_frame(audio[i * f : (i + 1) * f]) for i in range(n)]
        min_speech = max(1, self.cfg.min_speech_ms // self.cfg.frame_ms)
        hang = max(1, self.cfg.hangover_ms // self.cfg.frame_ms)
        segs: list[Segment] = []
        start: int | None = None
        run = silence = 0
        for i, s in enumerate(flags):
            if s:
                run += 1
                silence = 0
                if start is None and run >= min_speech:
                    start = i - run + 1
            else:
                silence += 1
                run = 0
                if start is not None and silence >= hang:
                    segs.append(Segment(start * f / self.cfg.sample_rate, (i - silence + 1) * f / self.cfg.sample_rate))
                    start = None
        if start is not None:
            segs.append(Segment(start * f / self.cfg.sample_rate, n * f / self.cfg.sample_rate))
        return segs

    def feed(self, frame: np.ndarray) -> bool:
        """Streaming: returns True on speech onset (used for barge-in / speech cancellation)."""
        onset = False
        if self.is_speech_frame(frame):
            self._speech_frames += 1
            self._silence_frames = 0
            if not self.in_speech and self._speech_frames * self.cfg.frame_ms >= self.cfg.min_speech_ms:
                self.in_speech, onset = True, True
        else:
            self._silence_frames += 1
            if self.in_speech and self._silence_frames * self.cfg.frame_ms >= self.cfg.hangover_ms:
                self.in_speech = False
                self._speech_frames = 0
            elif not self.in_speech:
                self._speech_frames = 0
        return onset


class SileroVAD:
    """Silero VAD (snakers4/silero-vad, MIT) using the ONNX model that ships inside faster-whisper
    (``faster_whisper/assets/silero_vad_v6.onnx``) - no extra download. Batch segmentation of 16 kHz float32 audio.
    Neural, so far more robust to noise and music than :class:`EnergyVAD`; slower (~1-3 ms per 30 ms frame on CPU)."""

    name = "silero"

    def __init__(self, *, sample_rate: int = 16000, threshold: float = 0.5, min_speech_ms: int = 250, min_silence_ms: int = 500, speech_pad_ms: int = 200) -> None:
        if sample_rate != 16000:
            raise ValueError("SileroVAD here expects 16 kHz audio")
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.min_speech_ms = min_speech_ms
        self.min_silence_ms = min_silence_ms
        self.speech_pad_ms = speech_pad_ms

    @staticmethod
    def available() -> tuple[bool, str]:
        try:
            from faster_whisper.vad import get_speech_timestamps  # noqa: F401
        except ImportError:
            return False, "Silero VAD needs faster-whisper (which bundles the ONNX model and onnxruntime)"
        return True, "silero_vad_v6.onnx via faster-whisper"

    def process(self, audio: np.ndarray) -> list[Segment]:
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        opts = VadOptions(threshold=self.threshold, min_speech_duration_ms=self.min_speech_ms, min_silence_duration_ms=self.min_silence_ms, speech_pad_ms=self.speech_pad_ms)
        stamps = get_speech_timestamps(np.asarray(audio, dtype=np.float32), opts, sampling_rate=self.sample_rate)
        return [Segment(s["start"] / self.sample_rate, s["end"] / self.sample_rate) for s in stamps]


def make_vad(kind: str = "auto", sample_rate: int = 16000) -> EnergyVAD | SileroVAD:
    """'silero' (raises if unavailable), 'energy', or 'auto' (Silero when installed, else energy)."""
    if kind not in ("auto", "silero", "energy"):
        raise ValueError("vad kind must be auto, silero or energy")
    if kind == "energy":
        return EnergyVAD(VadConfig(sample_rate=sample_rate))
    ok, msg = SileroVAD.available()
    if ok:
        return SileroVAD(sample_rate=sample_rate)
    if kind == "silero":
        raise RuntimeError(msg)
    return EnergyVAD(VadConfig(sample_rate=sample_rate))
