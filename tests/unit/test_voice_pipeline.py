"""Local voice pipeline (VAD -> STT -> respond -> TTS) with fake models: stage timings, silence, cancellation,
audio validation, model failure recovery, barge-in. Real Silero VAD is exercised when faster-whisper is installed."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import numpy as np
import pytest
from sellagent_speech.pipeline import BargeInMonitor, VoicePipeline, validate_audio, word_error_rate
from sellagent_speech.vad import EnergyVAD, SileroVAD, VadConfig, make_vad

SR = 16000


def _tone(seconds: float, amp: float = 0.3) -> np.ndarray:
    t = np.linspace(0, seconds, int(SR * seconds), endpoint=False)
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _speechlike() -> np.ndarray:
    z = np.zeros(int(SR * 0.5), dtype=np.float32)
    return np.concatenate([z, _tone(1.0), z])


class FakeSTT:
    def __init__(self, text: str = "price kitna hai", fail: bool = False, cancel: threading.Event | None = None) -> None:
        self.text, self.fail, self.cancel, self.calls = text, fail, cancel, 0

    def transcribe(self, audio, *, language=None, allow_download=False):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.fail:
            raise RuntimeError("model crashed")
        if self.cancel is not None:
            self.cancel.set()  # operator cancels while STT is running
        return SimpleNamespace(text=self.text, language=language or "hi")


class FakeTTS:
    def synthesize(self, text, voice):  # type: ignore[no-untyped-def]
        return SimpleNamespace(audio=np.zeros(22050, dtype=np.float32), sample_rate=22050)


def _pipe(stt=None, tts=None) -> VoicePipeline:  # type: ignore[no-untyped-def]
    return VoicePipeline(vad=EnergyVAD(VadConfig()), stt=stt or FakeSTT(), tts=tts or FakeTTS(), respond=lambda text, lang: (f"reply to {text}", lang or "en"), voices={"en": "en-voice", "hi": "hi-voice"})


def test_full_turn_records_every_stage_timing():
    turn = _pipe().run(_speechlike(), language="hi")
    assert turn.status == "ok", turn.error
    assert turn.transcript == "price kitna hai" and turn.reply_text == "reply to price kitna hai" and turn.reply_language == "hi"
    assert set(turn.timings_ms) >= {"vad", "stt", "respond", "tts", "total"}
    assert turn.reply_audio is not None and turn.to_dict()["reply_audio_s"] == pytest.approx(1.0)
    assert len(turn.segments) == 1 and 0.4 < turn.segments[0][0] < 0.6


def test_silence_is_no_speech_and_stt_is_never_called():
    stt = FakeSTT()
    turn = _pipe(stt=stt).run(np.zeros(SR * 2, dtype=np.float32))
    assert turn.status == "no_speech" and stt.calls == 0


def test_cancel_between_stages_stops_before_reply():
    cancel = threading.Event()
    turn = _pipe(stt=FakeSTT(cancel=cancel)).run(_speechlike(), cancel=cancel)
    assert turn.status == "cancelled" and turn.stage == "respond" and turn.reply_text == "" and turn.reply_audio is None


def test_model_failure_is_reported_not_raised():
    turn = _pipe(stt=FakeSTT(fail=True)).run(_speechlike())
    assert turn.status == "error" and turn.stage == "stt" and "model crashed" in turn.error


@pytest.mark.parametrize("bad", [np.zeros((2, SR), dtype=np.float32), np.zeros(100, dtype=np.float32), np.full(SR, np.nan, dtype=np.float32), np.zeros(SR * 61, dtype=np.float32)])
def test_invalid_audio_rejected(bad):
    with pytest.raises(ValueError):
        validate_audio(bad)
    assert _pipe().run(bad).status == "error"


def test_validate_normalises_int_like_and_clipped_input():
    a = validate_audio((np.ones(SR) * 2).astype(np.float64))
    assert a.dtype == np.float32 and float(np.max(np.abs(a))) == pytest.approx(1.0)


def test_barge_in_triggers_on_incoming_speech_only():
    m = BargeInMonitor()
    for _ in range(20):
        assert m.feed(np.zeros(480, dtype=np.float32)) is False
    hit = [m.feed(c) for c in np.array_split(_tone(0.5), 10)]
    assert any(hit) and m.triggered


def test_word_error_rate():
    assert word_error_rate("Hello, can you hear me?", "hello can you hear me") == 0.0
    assert word_error_rate("a b c d", "a x c") == pytest.approx(0.5)
    assert word_error_rate("", "") == 0.0


def test_make_vad_choices():
    assert make_vad("energy").name == "energy"
    with pytest.raises(ValueError):
        make_vad("nope")
    ok, _ = SileroVAD.available()
    assert make_vad("auto").name == ("silero" if ok else "energy")


def test_silero_vad_real_model_on_silence_and_noise():
    ok, msg = SileroVAD.available()
    if not ok:
        pytest.skip(msg)
    vad = SileroVAD()
    assert vad.process(np.zeros(SR * 2, dtype=np.float32)) == []
    rng = np.random.default_rng(0)
    # steady low-level noise is not speech for a neural VAD (an energy VAD would fire at this level)
    assert vad.process((0.02 * rng.standard_normal(SR * 2)).astype(np.float32)) == []
