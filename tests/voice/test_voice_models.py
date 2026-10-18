"""Opt-in real-model voice suite (Hindi and English tested separately). See tests/voice/README.md."""

from __future__ import annotations

import json
import os
import statistics
import time
import wave
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.model

PHRASES = {
    "en": ["Hello, this is an automated assistant calling for FITRON gym accounting software.", "How do you manage member payments at your gym today?", "The professional plan is one thousand nine hundred ninety nine rupees per month."],
    "hi": ["नमस्ते, मैं FITRON की ओर से एक स्वचालित सहायक बोल रहा हूँ।", "आप अपने जिम में मेंबर पेमेंट कैसे संभालते हैं?", "क्या आप एक छोटा डेमो देखना चाहेंगे?"],
}
MAX_WER = {"en": 0.25, "hi": 0.45}
AUDIO_DIR = Path(__file__).parent / "audio"


@pytest.fixture(scope="module")
def stack():
    if os.environ.get("SELLAGENT_VOICE_TESTS") != "1":
        pytest.skip("voice model suite disabled (set SELLAGENT_VOICE_TESTS=1; see tests/voice/README.md)")
    from sellagent_speech import FasterWhisperSTT, PiperTTS
    from sellagent_speech.vad import make_vad

    models = Path(os.environ.get("SELLAGENT_MODELS_DIR", "models"))
    stt = FasterWhisperSTT(os.environ.get("SELLAGENT_WHISPER", "small"), models_dir=models)
    ok, msg = stt.available()
    if not ok:
        pytest.skip(msg)
    t0 = time.perf_counter()
    stt.load(allow_download=False)
    return {"stt": stt, "tts": PiperTTS(models), "vad": make_vad("auto"), "load_ms": (time.perf_counter() - t0) * 1000,
            "voices": {"en": os.environ.get("SELLAGENT_VOICE_EN", ""), "hi": os.environ.get("SELLAGENT_VOICE_HI", "")}}


def _recorded(lang: str) -> list[tuple[str, np.ndarray]]:
    out = []
    for wav in sorted((AUDIO_DIR / lang).glob("*.wav")):
        ref = wav.with_suffix(".txt")
        if not ref.exists():
            continue
        with wave.open(str(wav), "rb") as w:
            rate, ch, data = w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())
        a = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        if ch > 1:
            a = a.reshape(-1, ch).mean(axis=1)
        from sellagent_speech.audio_io import resample

        out.append((ref.read_text(encoding="utf-8").strip(), resample(a, rate, 16000)))
    return out


@pytest.mark.parametrize("lang", ["en", "hi"])
def test_language_wer_and_latency(stack, lang, tmp_path):
    from sellagent_speech.audio_io import resample
    from sellagent_speech.pipeline import VoicePipeline, word_error_rate

    pipe = VoicePipeline(vad=stack["vad"], stt=stack["stt"], tts=None, respond=lambda _text, detected: ("", detected or lang))
    cases: list[tuple[str, str, np.ndarray]] = []
    voice = stack["voices"][lang]
    if voice:
        for phrase in PHRASES[lang]:
            t = stack["tts"].synthesize(phrase, voice)
            cases.append(("synthetic", phrase, resample(t.audio, t.sample_rate, 16000)))
    cases += [("recorded", ref, a) for ref, a in _recorded(lang)]
    if not cases:
        pytest.skip(f"no Piper voice for {lang} (SELLAGENT_VOICE_{lang.upper()}) and no recordings in tests/voice/audio/{lang}")
    rows = []
    for kind, ref, audio in cases:
        turn = pipe.run(audio, language=lang, synthesize=False)
        rows.append({"kind": kind, "reference": ref, "transcript": turn.transcript, "status": turn.status, "error": turn.error,
                     "wer": word_error_rate(ref, turn.transcript) if turn.status == "ok" else 1.0, "timings_ms": turn.timings_ms, "vad": turn.vad_engine})
    report = {"language": lang, "whisper_model": stack["stt"].model_size, "model_load_ms": stack["load_ms"], "cases": rows,
              "mean_wer": statistics.mean(r["wer"] for r in rows), "mean_stt_ms": statistics.mean(r["timings_ms"].get("stt", 0) for r in rows)}
    out_dir = Path(os.environ.get("SELLAGENT_VOICE_REPORT_DIR", tmp_path))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"voice_{lang}_{time.strftime('%Y%m%d-%H%M%S')}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("language", "whisper_model", "mean_wer", "mean_stt_ms")}, ensure_ascii=False))
    assert all(r["status"] == "ok" for r in rows), [r for r in rows if r["status"] != "ok"]
    assert report["mean_wer"] <= MAX_WER[lang], f"{lang} mean WER {report['mean_wer']:.2f} > {MAX_WER[lang]}"
