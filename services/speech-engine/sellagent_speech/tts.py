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
    """Piper TTS. ``executable`` set: run an operator-installed ``piper`` program as a separate process (keeps the
    GPL-3.0 piper code out of the proprietary bundle; see LICENSES/README.md). Otherwise import ``piper`` in-process
    (development installs from requirements-speech.txt)."""

    def __init__(self, models_dir: Path, executable: str | None = None) -> None:
        self.models_dir = Path(models_dir) / "piper"
        self.executable = executable
        self._voices: dict[str, object] = {}

    def available(self) -> tuple[bool, str]:
        voices = self.list_voices()
        if self.executable:
            if not Path(self.executable).exists():
                return False, f"piper executable not found: {self.executable}"
            return True, f"piper subprocess {self.executable}; {len(voices)} voice(s) in {self.models_dir}"
        try:
            import piper  # noqa: F401
        except ImportError:
            return False, "piper-tts is not installed (pip install -r requirements-speech.txt) and ai.piper_executable is not set"
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

    def synthesize(self, text: str, voice: str, speed: float = 1.0, *, volume: float = 1.0, pause_ms: int = 0) -> TTSResult:
        """``speed`` 0.5-2.0 (1.0 = natural pace, Piper length_scale = 1 / speed); ``volume`` 0.2-1.5 gain;
        ``pause_ms`` silence inserted after each sentence for natural pacing."""
        if not text.strip():
            raise ValueError("text is empty")
        speed = min(2.0, max(0.5, float(speed)))
        volume = min(1.5, max(0.2, float(volume)))
        pause_ms = max(0, min(1500, int(pause_ms)))
        if self.executable:
            return self._synthesize_subprocess(text, voice, speed, volume, pause_ms)
        v = self._voice(voice)
        t0 = time.perf_counter()
        chunks: list[np.ndarray] = []
        rate = 22050
        try:
            from piper import SynthesisConfig

            stream = v.synthesize(text, syn_config=SynthesisConfig(length_scale=1.0 / speed, volume=volume))
        except ImportError:  # older piper: no per-call config
            stream = v.synthesize(text)
        for chunk in stream:  # piper >= 1.3 yields AudioChunk objects
            arr = getattr(chunk, "audio_float_array", None)
            if arr is None:
                raw = getattr(chunk, "audio_int16_bytes", None) or bytes(chunk)
                arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            rate = getattr(chunk, "sample_rate", rate)
            if chunks and pause_ms:
                chunks.append(np.zeros(int(rate * pause_ms / 1000), dtype=np.float32))  # piper yields one chunk per sentence
            chunks.append(np.asarray(arr, dtype=np.float32))
        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        return TTSResult(audio=audio, sample_rate=int(rate), latency_ms=(time.perf_counter() - t0) * 1000, voice=voice, text=text)

    def _synthesize_subprocess(self, text: str, voice: str, speed: float, volume: float = 1.0, pause_ms: int = 0) -> TTSResult:
        import subprocess
        import tempfile
        import wave

        path = self.models_dir / f"{voice}.onnx"
        if not path.exists():
            raise TTSUnavailable(f"voice {voice!r} not found in {self.models_dir} (see models/README.md)")
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "tts.wav"
            cmd = [str(self.executable), "--model", str(path), "--output_file", str(out), "--length-scale", f"{1.0 / speed:.3f}", "--volume", f"{volume:.2f}", "--sentence-silence", f"{pause_ms / 1000:.2f}"]
            try:
                proc = subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True, timeout=60, check=False)  # noqa: S603 - fixed argv, no shell
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise TTSUnavailable(f"piper process failed: {exc}") from exc
            if proc.returncode != 0 or not out.exists():
                raise TTSUnavailable(f"piper exited {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')[-300:]}")
            with wave.open(str(out), "rb") as w:
                rate, frames = w.getframerate(), w.readframes(w.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        return TTSResult(audio=audio, sample_rate=int(rate), latency_ms=(time.perf_counter() - t0) * 1000, voice=voice, text=text)
