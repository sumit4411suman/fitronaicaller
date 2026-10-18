"""Speech-to-text via faster-whisper (CTranslate2, CPU int8). Lazy import so the backend runs without it."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class STTUnavailable(RuntimeError):
    pass


@dataclass
class STTResult:
    text: str
    language: str
    language_probability: float
    duration_s: float
    latency_ms: float
    model: str
    segments: list[dict]


class FasterWhisperSTT:
    def __init__(self, model_size: str = "small", models_dir: Path | None = None, compute_type: str = "int8", cpu_threads: int = 4) -> None:
        self.model_size = model_size
        self.models_dir = models_dir
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self._model = None
        self.load_ms: float | None = None

    def available(self) -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False, "faster-whisper is not installed (pip install -r requirements-speech.txt)"
        if self.models_dir and not any(self.models_dir.glob(f"**/*{self.model_size}*")) and not self._model:
            return True, f"faster-whisper installed; model '{self.model_size}' not found in {self.models_dir} (will download only if external network is enabled)"
        return True, "faster-whisper installed"

    def load(self, *, allow_download: bool) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise STTUnavailable("faster-whisper not installed") from exc
        t0 = time.perf_counter()
        kwargs = {"device": "cpu", "compute_type": self.compute_type, "cpu_threads": self.cpu_threads}
        if self.models_dir:
            kwargs["download_root"] = str(self.models_dir)
        kwargs["local_files_only"] = not allow_download
        try:
            self._model = WhisperModel(self.model_size, **kwargs)
        except Exception as exc:  # noqa: BLE001
            raise STTUnavailable(f"could not load whisper model '{self.model_size}': {exc}") from exc
        self.load_ms = (time.perf_counter() - t0) * 1000

    def transcribe(self, audio_16k: np.ndarray, *, language: str | None = None, allow_download: bool = False) -> STTResult:
        """``audio_16k``: float32 mono at 16 kHz. ``language``: 'hi', 'en' or None for auto-detect."""
        self.load(allow_download=allow_download)
        assert self._model is not None
        t0 = time.perf_counter()
        segments, info = self._model.transcribe(audio_16k, language=language, beam_size=1, vad_filter=True, condition_on_previous_text=False)
        segs = [{"start": s.start, "end": s.end, "text": s.text.strip(), "avg_logprob": s.avg_logprob} for s in segments]
        text = " ".join(s["text"] for s in segs).strip()
        return STTResult(text=text, language=info.language, language_probability=float(info.language_probability), duration_s=float(info.duration), latency_ms=(time.perf_counter() - t0) * 1000, model=self.model_size, segments=segs)
