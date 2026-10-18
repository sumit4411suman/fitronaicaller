"""Text-to-speech via Piper (ONNX, CPU). Lazy import. Voices are .onnx + .onnx.json files in models_dir/piper."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class TTSUnavailable(RuntimeError):
    pass


@dataclass
class TTSResult:
    audio: np.ndarray  # float32 mono
    sample_rate: int
    latency_ms: float
    voice: str
    text: str


class PiperTTS:
    def __init__(self, models_dir: Path) -> None:
        self.models_dir = Path(models_dir) / "piper"
        self._voices: dict[str, object] = {}

    def available(self) -> tuple[bool, str]:
        try:
            import piper  # noqa: F401
        except ImportError:
            return False, "piper-tts is not installed (pip install -r requirements-speech.txt)"
        voices = self.list_voices()
        return True, f"piper installed; {len(voices)} voice(s) found in {self.models_dir}"

    def list_voices(self) -> list[dict]:
        if not self.models_dir.exists():
            return []
        out = []
        for onnx in sorted(self.models_dir.glob("*.onnx")):
            cfg = onnx.with_suffix(".onnx.json")
            out.append({"name": onnx.stem, "path": str(onnx), "has_config": cfg.exists(), "size_bytes": onnx.stat().st_size, "language": onnx.stem.split("_")[0] if "_" in onnx.stem else "unknown"})
        return out

    def _voice(self, name: str):  # type: ignore[no-untyped-def]
        if name in self._voices:
            return self._voices[name]
        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise TTSUnavailable("piper-tts not installed") from exc
        path = self.models_dir / f"{name}.onnx"
        if not path.exists() or not path.with_suffix(".onnx.json").exists():
            raise TTSUnavailable(f"voice {name!r} not found in {self.models_dir} (see models/README.md)")
        v = PiperVoice.load(str(path), config_path=str(path.with_suffix(".onnx.json")))
        self._voices[name] = v
        return v

    def synthesize(self, text: str, voice: str) -> TTSResult:
        if not text.strip():
            raise ValueError("text is empty")
        v = self._voice(voice)
        t0 = time.perf_counter()
        chunks: list[np.ndarray] = []
        rate = 22050
        for chunk in v.synthesize(text):  # piper >= 1.3 yields AudioChunk objects
            arr = getattr(chunk, "audio_float_array", None)
            if arr is None:
                raw = getattr(chunk, "audio_int16_bytes", None) or bytes(chunk)
                arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            rate = getattr(chunk, "sample_rate", rate)
            chunks.append(np.asarray(arr, dtype=np.float32))
        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        return TTSResult(audio=audio, sample_rate=int(rate), latency_ms=(time.perf_counter() - t0) * 1000, voice=voice, text=text)
