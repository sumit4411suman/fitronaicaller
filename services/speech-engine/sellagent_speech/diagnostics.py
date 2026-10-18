"""Local speech-pipeline diagnostics (PC side). Everything here is SIMULATED or LOCAL-ONLY and is labelled as such.
It proves that STT/TTS/VAD run on the PC; it proves nothing about cellular call audio on the phone."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from sellagent_speech.audio_io import resample
from sellagent_speech.stt import FasterWhisperSTT, STTUnavailable
from sellagent_speech.tts import PiperTTS, TTSUnavailable
from sellagent_speech.vad import EnergyVAD, VadConfig

TEST_PHRASES = {
    "en": ["Hello, this is a test call from FITRON gym accounting software.", "Can you hear me clearly?"],
    "hi": ["नमस्ते, यह FITRON जिम अकाउंटिंग सॉफ़्टवेयर की ओर से एक परीक्षण कॉल है।", "क्या आप मुझे साफ़ सुन पा रहे हैं?"],
}


@dataclass
class LoopbackResult:
    kind: str  # always "simulated_loopback"
    language: str
    phrase: str
    tts_voice: str | None
    tts_latency_ms: float | None
    stt_model: str | None
    stt_latency_ms: float | None
    transcript: str | None
    word_overlap: float | None
    vad_segments: int | None
    error: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def _overlap(a: str, b: str) -> float:
    wa, wb = set(a.lower().split()), set(b.lower().split())
    return len(wa & wb) / max(1, len(wa))


def tts_to_stt_loopback(models_dir: Path, *, language: str, voice: str | None, whisper_model: str, allow_download: bool = False) -> list[LoopbackResult]:
    """Synthesize with Piper, run VAD, transcribe with Whisper, compare. Labelled simulated: no phone, no call."""
    out: list[LoopbackResult] = []
    tts = PiperTTS(models_dir)
    stt = FasterWhisperSTT(whisper_model, models_dir=models_dir)
    for phrase in TEST_PHRASES[language]:
        res = LoopbackResult("simulated_loopback", language, phrase, voice, None, whisper_model, None, None, None, None, None)
        try:
            if not voice:
                raise TTSUnavailable(f"no Piper voice configured for language {language!r}")
            t = tts.synthesize(phrase, voice)
            res.tts_latency_ms = t.latency_ms
            audio16 = resample(t.audio, t.sample_rate, 16000)
            res.vad_segments = len(EnergyVAD(VadConfig()).process(audio16))
            s = stt.transcribe(audio16, language=language, allow_download=allow_download)
            res.stt_latency_ms, res.transcript = s.latency_ms, s.text
            res.word_overlap = _overlap(phrase, s.text)
        except (TTSUnavailable, STTUnavailable, ValueError) as exc:
            res.error = str(exc)
        out.append(res)
    return out


def synthetic_vad_selftest() -> dict:
    """Automated: tone bursts with silence in between must yield the expected segment count."""
    sr = 16000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    silence = np.zeros(int(sr * 0.6), dtype=np.float32)
    audio = np.concatenate([silence, tone, silence, tone, silence])
    t0 = time.perf_counter()
    segs = EnergyVAD(VadConfig()).process(audio)
    return {"kind": "automated_synthetic", "expected_segments": 2, "segments": len(segs), "ok": len(segs) == 2, "latency_ms": (time.perf_counter() - t0) * 1000}
