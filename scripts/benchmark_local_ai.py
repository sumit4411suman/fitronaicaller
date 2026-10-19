#!/usr/bin/env python3
"""Benchmark SELL AGENT's LOCAL AI latency on this PC (CPU-only) — real numbers, no fabrication.

It measures the actual local pipeline Priya uses on a call:

    caller audio ─► VAD ─► faster-whisper (STT) ─► conversation engine ─► Piper (TTS) ─► reply audio

To avoid needing you to record anything, it uses **Piper to synthesize the "caller" utterance**, then feeds that
audio back through the real pipeline and times every stage. All inference runs locally on this machine, so the
latency figures are genuine for your CPU. It reports per-stage latency (STT / engine / TTS / total), cold model
load time, and memory, split by Hindi and English, over several runs.

Honest caveats (printed in the report too):
  * Piper-synthesized speech is cleaner than a real phone caller, so the STT **accuracy** (WER) here is
    optimistic; treat WER as a sanity check, not a field number. The **latency** figures are representative,
    because they are real model inference on this CPU.
  * The first run of each model includes load/warm-up and is reported separately, not mixed into the steady-state
    percentiles.
  * Pass --llm to benchmark with a local LLM (Ollama/llama.cpp); the default is the no-LLM script engine, whose
    "engine" stage is near-zero by design.

Usage (on the PC, after models are installed):
    python scripts/download_models.py --whisper small base --piper hi_IN-priyamvada-medium en_US-lessac-medium --yes
    python scripts/benchmark_local_ai.py --runs 5 --out benchmark.json
    python scripts/benchmark_local_ai.py --whisper small base --runs 5   # compare two Whisper sizes side by side
    python scripts/benchmark_local_ai.py --runs 5 --llm                   # include the local LLM in the engine stage
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in ("services/local-backend", "services/ai-engine", "services/speech-engine", "services/knowledge-base", "packages/shared-protocol"):
    sys.path.insert(0, str(_ROOT / _p))

# English and Hindi probe utterances a gym owner might say (short, mid, longer).
PHRASES = {
    "en": ["Hello, who is this?", "We already use Excel for our billing.", "How much does FITRON cost per month and what do I get?"],
    "hi": ["नमस्ते, कौन बोल रहा है?", "हम अभी एक्सेल इस्तेमाल करते हैं।", "FITRON की कीमत कितनी है और इसमें क्या-क्या मिलता है?"],
}


# --------------------------------------------------------------------------- pure stats (unit-tested)
def percentile(values: list[float], p: float) -> float:
    """Linear-interpolated percentile (p in 0..100). Pure; empty -> 0.0."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def summarize(samples: list[float]) -> dict[str, float]:
    """min / median / mean / p95 / max / n for a list of latency samples (ms). Pure."""
    if not samples:
        return {"n": 0, "min": 0.0, "median": 0.0, "mean": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "n": len(samples),
        "min": round(min(samples), 1),
        "median": round(statistics.median(samples), 1),
        "mean": round(statistics.fmean(samples), 1),
        "p95": percentile(samples, 95),
        "max": round(max(samples), 1),
    }


def rss_mb() -> float | None:
    """Current resident memory in MB, cross-platform best-effort (psutil, then resource). None if unavailable."""
    try:
        import psutil  # type: ignore[import-untyped]

        return round(psutil.Process().memory_info().rss / 1e6, 1)
    except Exception:  # noqa: BLE001, S110 - psutil optional; fall through to resource
        pass
    try:
        import resource  # unix only

        maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KB, macOS reports bytes.
        return round((maxrss / 1024 if maxrss > 1e7 else maxrss) / 1024, 1)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- benchmark
def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark SELL AGENT local AI latency on this PC")
    ap.add_argument("--whisper", nargs="+", default=["small"], help="faster-whisper model size(s); pass several to compare, e.g. --whisper small base")
    ap.add_argument("--models-dir", default=None)
    ap.add_argument("--voice-en", default="en_US-lessac-medium")
    ap.add_argument("--voice-hi", default="hi_IN-priyamvada-medium")
    ap.add_argument("--runs", type=int, default=5, help="measured runs per phrase (after a warm-up run)")
    ap.add_argument("--llm", action="store_true", help="use a local LLM for the engine stage (default: script engine)")
    ap.add_argument("--out", default=None, help="write the JSON report here")
    a = ap.parse_args()

    import numpy as np
    from sellagent_ai.conversation import (
        ConversationContext,
        ConversationEngine,
        ConversationStateMachine,
        KnowledgeFact,
        State,
    )
    from sellagent_ai.persona import ConversationMemory, Persona
    from sellagent_backend.config import Settings
    from sellagent_kb.service import FITRON_SEED
    from sellagent_speech import FasterWhisperSTT, PiperTTS
    from sellagent_speech.audio_io import resample
    from sellagent_speech.pipeline import VoicePipeline, word_error_rate
    from sellagent_speech.vad import EnergyVAD, VadConfig

    models_dir = Path(a.models_dir) if a.models_dir else Settings().models_dir
    tts = PiperTTS(models_dir)
    ok, msg = tts.available()
    if not ok:
        print(f"Voice (Piper) not ready: {msg}\nInstall a Hindi + English voice with scripts/download_models.py.")
        return 3
    voices = {"en": a.voice_en, "hi": a.voice_hi}

    facts = [KnowledgeFact(f"kb:seed{i}#v1", e["title"], e["category"], e["body"], e.get("structured")) for i, e in enumerate(FITRON_SEED) if e.get("approved", False)]
    persona = Persona()
    llm = None
    if a.llm:
        from sellagent_ai.llm import make_provider
        s = Settings()
        llm = make_provider(getattr(s, "ai_llm_provider", "none"), ollama_url=s.ollama_base_url, llamacpp_url=s.llamacpp_base_url)
    engine = ConversationEngine(llm, use_llm=bool(a.llm))

    def respond(text: str, lang: str | None) -> tuple[str, str]:
        sm = ConversationStateMachine(State.CONNECTED)
        turn = engine.respond(sm, text, facts=facts, ctx=ConversationContext(authorized=True),
                              preferred_language=lang if lang in ("hi", "en") else "en",
                              contact_person="Rahul", business_name="Power Gym", persona=persona, memory=ConversationMemory())
        return turn.agent_text, (turn.language if turn.language in ("hi", "en") else (lang or "en"))

    # Pre-synthesize each probe utterance ONCE (TTS is model-independent), so every Whisper size transcribes the
    # exact same audio - a fair STT comparison.
    probes: list[tuple[str, str, np.ndarray]] = []
    try:
        for lang, phrases in PHRASES.items():
            for phrase in phrases:
                synth = tts.synthesize(phrase, voices[lang])
                probes.append((lang, phrase, resample(np.asarray(synth.audio, dtype=np.float32), synth.sample_rate, 16000)))
    except Exception as exc:  # noqa: BLE001 - never fabricate; a missing voice is a clean, actionable failure
        print(f"Could not synthesize the probe audio (Piper voice missing?): {exc.__class__.__name__}: {exc}\n"
              f"Install the voices: python scripts/download_models.py --piper {a.voice_hi} {a.voice_en} --yes")
        return 3

    def measure(size: str) -> dict | None:
        """Benchmark one Whisper size against the shared probes. Returns a result dict, or None on a load failure
        (message printed). Never fabricates numbers."""
        stt = FasterWhisperSTT(size, models_dir=models_dir)
        pipe = VoicePipeline(vad=EnergyVAD(VadConfig(sample_rate=16000)), stt=stt, tts=tts, respond=respond, voices=voices, allow_download=False)
        rss_before = rss_mb()
        try:
            t0 = time.perf_counter()
            stt.transcribe(probes[0][2], language=probes[0][0], allow_download=False)  # force model load
            cold_ms = round((time.perf_counter() - t0) * 1000, 1)
        except Exception as exc:  # noqa: BLE001 - never fabricate numbers from a failed load
            print(f"Whisper '{size}' could not load: {exc.__class__.__name__}: {exc}\n"
                  f"  Install it: python scripts/download_models.py --whisper {size} --piper {a.voice_hi} {a.voice_en} --yes")
            return None
        per_stage: dict[str, list[float]] = {"stt": [], "respond": [], "tts": [], "total": []}
        by_lang: dict[str, list[float]] = {"en": [], "hi": []}
        wers: list[float] = []
        errors: list[str] = []
        for lang, phrase, audio16 in probes:
            pipe.run(audio16, language=lang)  # warm-up (discarded)
            for _ in range(a.runs):
                turn = pipe.run(audio16, language=lang)
                if turn.status == "error":
                    errors.append(f"{lang}: {turn.error}")
                    continue
                for stage in ("stt", "respond", "tts", "total"):
                    if stage in turn.timings_ms:
                        per_stage[stage].append(turn.timings_ms[stage])
                by_lang[lang].append(turn.timings_ms.get("total", 0.0))
                if turn.transcript:
                    wers.append(word_error_rate(phrase, turn.transcript))
        return {
            "whisper": size,
            "stt_cold_load_ms": cold_ms,
            "latency_ms": {stage: summarize(vals) for stage, vals in per_stage.items()},
            "total_ms_by_language": {lang: summarize(vals) for lang, vals in by_lang.items()},
            "stt_accuracy": {"mean_wer": round(statistics.fmean(wers), 3) if wers else None, "n": len(wers), "note": "optimistic: clean synthesized audio, not a real phone caller"},
            "memory_mb": {"rss_before_stt": rss_before, "rss_after": rss_mb()},
            "errors": errors[:10],
        }

    report: dict = {
        "tool": "benchmark_local_ai", "generated_at": datetime.now(UTC).isoformat(),
        "machine": {"platform": sys.platform, "cpu_threads_requested": 4},
        "config": {"whisper": a.whisper, "voices": voices, "runs_per_phrase": a.runs, "llm": bool(a.llm)},
        "label": "REAL local inference on this CPU. Latency is representative; WER is optimistic (Piper-clean audio).",
        "models": {},
    }
    for size in a.whisper:
        res = measure(size)
        if res is not None:
            report["models"][size] = res
    if not report["models"]:
        return 3

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if a.out:
        Path(a.out).write_text(text)

    # Human-readable summary, per model then a comparison.
    print("\n=== SELL AGENT local AI latency (this PC) ===")
    print(f"Voices: {voices['hi']}/{voices['en']}  |  llm={'on' if a.llm else 'off (script engine)'}  |  runs/phrase={a.runs}")
    for size, res in report["models"].items():
        lat = res["latency_ms"]
        print(f"\n--- whisper={size}  (STT cold load {res['stt_cold_load_ms']} ms) ---")
        print(f"{'stage':<10}{'median':>10}{'mean':>10}{'p95':>10}{'max':>10}   (ms, n={lat['total']['n']})")
        for stage in ("stt", "respond", "tts", "total"):
            s = lat[stage]
            print(f"{stage:<10}{s['median']:>10}{s['mean']:>10}{s['p95']:>10}{s['max']:>10}")
        tb = res["total_ms_by_language"]
        wer = res["stt_accuracy"]["mean_wer"]
        print(f"total by language: EN median {tb['en']['median']} ms, HI median {tb['hi']['median']} ms"
              + (f"  |  WER(optimistic) {wer}" if wer is not None else ""))
        if res["errors"]:
            print(f"WARNING: {len(res['errors'])} run(s) errored; see the report.")
    if len(report["models"]) > 1:
        print(f"\n=== comparison ===\n{'whisper':<10}{'STT median':>12}{'total median':>14}{'cold load':>12}   (ms)")
        for size, res in report["models"].items():
            print(f"{size:<10}{res['latency_ms']['stt']['median']:>12}{res['latency_ms']['total']['median']:>14}{res['stt_cold_load_ms']:>12}")
    if a.out:
        print(f"\nWrote full report to {a.out}")
    print("\nNote: latency is real for this CPU; WER is optimistic because the caller audio is Piper-clean, not a "
          "noisy phone line. Autonomous calling still needs the real-device two-way-audio gate (docs/JIO_DIRECT_CALLING.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
