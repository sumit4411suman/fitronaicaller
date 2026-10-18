"""POST /speech/pipeline-test with prerecorded WAV input. Models are faked here (no downloads in CI); the real
Hindi/English model suite is tests/voice (opt-in)."""

from __future__ import annotations

import io
import wave
from types import SimpleNamespace

import numpy as np
import sellagent_backend.api.v1.speech as speech_api


def _wav(seconds_silence: float = 0.5, seconds_tone: float = 1.0, rate: int = 22050) -> bytes:
    t = np.linspace(0, seconds_tone, int(rate * seconds_tone), endpoint=False)
    sig = np.concatenate([np.zeros(int(rate * seconds_silence)), 0.3 * np.sin(2 * np.pi * 220 * t), np.zeros(int(rate * seconds_silence))])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((sig * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


class FakeSTT:
    model_size = "fake"

    def __init__(self, *a, **k) -> None:  # type: ignore[no-untyped-def]
        pass

    def available(self):  # type: ignore[no-untyped-def]
        return True, "fake"

    def transcribe(self, audio, *, language=None, allow_download=False):  # type: ignore[no-untyped-def]
        assert audio.dtype == np.float32 and 0.9 < len(audio) / 16000 < 1.6  # VAD cropped the silence
        return SimpleNamespace(text="how much does it cost?", language="en")


class FakeTTS:
    def __init__(self, *a, **k) -> None:  # type: ignore[no-untyped-def]
        pass

    def available(self):  # type: ignore[no-untyped-def]
        return True, "fake"

    def synthesize(self, text, voice):  # type: ignore[no-untyped-def]
        return SimpleNamespace(audio=np.zeros(11025, dtype=np.float32), sample_rate=22050)


def test_pipeline_from_prerecorded_wav(client, monkeypatch):
    monkeypatch.setattr(speech_api, "FasterWhisperSTT", FakeSTT)
    monkeypatch.setattr(speech_api, "PiperTTS", FakeTTS)
    assert client.patch("/api/v1/settings", json={"values": {"ai.vad_engine": "energy"}}).status_code == 200
    r = client.post("/api/v1/speech/pipeline-test", params={"language": "en"}, files={"file": ("q.wav", _wav(), "audio/wav")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"].startswith("PRERECORDED_AUDIO") and "not call audio" in body["label"]
    assert body["status"] == "ok" and body["transcript"] == "how much does it cost?"
    assert "₹1,999" in body["reply_text"]  # price only from approved knowledge, guard-railed
    assert {"vad", "stt", "respond", "tts", "total"} <= set(body["timings_ms"]) and body["vad_engine"] == "energy"
    assert body["reply_wav_base64"]
    runs = client.get("/api/v1/ai/runs").json()
    assert any(x["provider"].startswith("pipeline:energy") for x in runs)


def test_pipeline_rejects_bad_input_and_reports_missing_models(client, monkeypatch):
    r = client.post("/api/v1/speech/pipeline-test", files={"file": ("x.wav", b"not a wav", "audio/wav")})
    assert r.status_code == 400 and r.json()["code"] == "bad_audio"
    assert client.patch("/api/v1/settings", json={"values": {"ai.vad_engine": "loud"}}).status_code == 400

    class Missing(FakeSTT):
        def available(self):  # type: ignore[no-untyped-def]
            return False, "faster-whisper is not installed"

    monkeypatch.setattr(speech_api, "FasterWhisperSTT", Missing)
    r = client.post("/api/v1/speech/pipeline-test", files={"file": ("q.wav", _wav(), "audio/wav")})
    assert r.status_code == 400 and r.json()["code"] == "stt_unavailable"
