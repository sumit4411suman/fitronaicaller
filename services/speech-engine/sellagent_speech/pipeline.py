"""Turn-based local voice pipeline, independent of any telephone path:

    input audio -> VAD -> speech-to-text -> respond(text) [conversation engine + guardrails] -> TTS -> output audio

Every stage is timed. A cancel event stops the turn between stages; :class:`BargeInMonitor` tells a player to stop
speaking as soon as incoming speech starts. Feeding it prerecorded files or a PC microphone proves the pipeline
only - it says nothing about access to cellular call audio on the phone.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from sellagent_speech.vad import EnergyVAD, Segment, VadConfig

SAMPLE_RATE = 16000
MIN_AUDIO_S = 0.3
MAX_AUDIO_S = 60.0


class _VAD(Protocol):
    name: str

    def process(self, audio: np.ndarray) -> list[Segment]: ...


@dataclass
class PipelineTurn:
    status: str  # ok | no_speech | cancelled | error
    transcript: str = ""
    language: str | None = None
    reply_text: str = ""
    reply_language: str | None = None
    reply_audio: np.ndarray | None = None
    reply_sample_rate: int | None = None
    segments: list[tuple[float, float]] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)
    vad_engine: str = ""
    error: str | None = None
    stage: str | None = None  # where it stopped (for cancelled / error)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "transcript": self.transcript, "language": self.language, "reply_text": self.reply_text, "reply_language": self.reply_language,
            "reply_audio_s": (len(self.reply_audio) / self.reply_sample_rate) if self.reply_audio is not None and self.reply_sample_rate else None,
            "segments": self.segments, "timings_ms": self.timings_ms, "vad_engine": self.vad_engine, "error": self.error, "stage": self.stage,
        }


def validate_audio(audio: Any) -> np.ndarray:
    """16 kHz mono float32 in [-1, 1], 0.3-60 s, finite. Raises ValueError otherwise."""
    a = np.asarray(audio)
    if a.ndim != 1:
        raise ValueError(f"audio must be mono 1-D, got shape {a.shape}")
    if a.dtype != np.float32:
        a = a.astype(np.float32)
    if not np.all(np.isfinite(a)):
        raise ValueError("audio contains NaN or infinite samples")
    dur = len(a) / SAMPLE_RATE
    if dur < MIN_AUDIO_S:
        raise ValueError(f"audio too short ({dur:.2f} s < {MIN_AUDIO_S} s)")
    if dur > MAX_AUDIO_S:
        raise ValueError(f"audio too long ({dur:.1f} s > {MAX_AUDIO_S} s)")
    peak = float(np.max(np.abs(a))) if len(a) else 0.0
    if peak > 1.0:
        a = a / peak
    return a


class VoicePipeline:
    def __init__(
        self, *, vad: _VAD, stt: Any, tts: Any | None, respond: Callable[[str, str | None], tuple[str, str]],
        voices: dict[str, str] | None = None, allow_download: bool = False,
    ) -> None:
        self.vad = vad
        self.stt = stt
        self.tts = tts
        self.respond = respond
        self.voices = voices or {}
        self.allow_download = allow_download

    def run(self, audio: Any, *, language: str | None = None, cancel: threading.Event | None = None, synthesize: bool = True) -> PipelineTurn:
        cancel = cancel or threading.Event()
        t_start = time.perf_counter()
        turn = PipelineTurn(status="ok", vad_engine=getattr(self.vad, "name", type(self.vad).__name__))

        def lap(stage: str, t0: float) -> None:
            turn.timings_ms[stage] = round((time.perf_counter() - t0) * 1000, 1)

        def stop(stage: str) -> bool:
            if cancel.is_set():
                turn.status, turn.stage = "cancelled", stage
                return True
            return False

        try:
            stage = "validate"
            a = validate_audio(audio)
            if stop(stage):
                return self._done(turn, t_start)
            stage, t0 = "vad", time.perf_counter()
            segs = self.vad.process(a)
            lap(stage, t0)
            turn.segments = [(round(s.start_s, 3), round(s.end_s, 3)) for s in segs]
            if not segs:
                turn.status = "no_speech"
                return self._done(turn, t_start)
            speech = a[int(segs[0].start_s * SAMPLE_RATE) : int(segs[-1].end_s * SAMPLE_RATE) + 1]
            if stop("stt"):
                return self._done(turn, t_start)
            stage, t0 = "stt", time.perf_counter()
            res = self.stt.transcribe(speech, language=language if language in ("hi", "en") else None, allow_download=self.allow_download)
            lap(stage, t0)
            turn.transcript, turn.language = (res.text or "").strip(), res.language
            if not turn.transcript:
                turn.status = "no_speech"
                return self._done(turn, t_start)
            if stop("respond"):
                return self._done(turn, t_start)
            stage, t0 = "respond", time.perf_counter()
            turn.reply_text, turn.reply_language = self.respond(turn.transcript, turn.language)
            lap(stage, t0)
            if not synthesize or self.tts is None or not turn.reply_text:
                return self._done(turn, t_start)
            if stop("tts"):
                return self._done(turn, t_start)
            stage, t0 = "tts", time.perf_counter()
            voice = self.voices.get(turn.reply_language or "en") or self.voices.get("en")
            if not voice:
                raise ValueError(f"no TTS voice configured for {turn.reply_language!r}")
            out = self.tts.synthesize(turn.reply_text, voice)
            lap(stage, t0)
            turn.reply_audio, turn.reply_sample_rate = out.audio, out.sample_rate
        except Exception as exc:  # noqa: BLE001 - any model/audio failure becomes a reported, recoverable turn
            turn.status, turn.stage, turn.error = "error", stage, f"{exc.__class__.__name__}: {exc}"[:400]
        return self._done(turn, t_start)

    @staticmethod
    def _done(turn: PipelineTurn, t_start: float) -> PipelineTurn:
        turn.timings_ms["total"] = round((time.perf_counter() - t_start) * 1000, 1)
        return turn


class BargeInMonitor:
    """Feed incoming audio frames while the agent is speaking; ``triggered`` turns true at the first speech onset so
    the player can stop immediately instead of talking over the other person."""

    def __init__(self, cfg: VadConfig | None = None) -> None:
        self.vad = EnergyVAD(cfg or VadConfig(min_speech_ms=150, hangover_ms=300))
        self.frame = self.vad._frame
        self._buf = np.zeros(0, dtype=np.float32)
        self.triggered = False

    def feed(self, chunk: np.ndarray) -> bool:
        self._buf = np.concatenate([self._buf, np.asarray(chunk, dtype=np.float32)])
        while len(self._buf) >= self.frame and not self.triggered:
            frame, self._buf = self._buf[: self.frame], self._buf[self.frame :]
            if self.vad.feed(frame):
                self.triggered = True
        return self.triggered


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein WER over whitespace tokens, punctuation stripped, case-folded."""
    import re

    def toks(s: str) -> list[str]:
        return [t for t in re.sub(r"[^\w\s]", " ", s.lower()).split() if t]

    r, h = toks(reference), toks(hypothesis)
    if not r:
        return 0.0 if not h else 1.0
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / len(r)
