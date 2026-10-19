"""Pure-stats tests for scripts/benchmark_local_ai.py (percentile / summarize). Headless: the heavy model
imports live inside main(), so importing the module only needs stdlib."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_local_ai.py"
_spec = importlib.util.spec_from_file_location("benchmark_local_ai", _SCRIPT)
assert _spec and _spec.loader
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


def test_percentile_basic():
    assert bench.percentile([], 95) == 0.0
    assert bench.percentile([42.0], 95) == 42.0
    assert bench.percentile([0, 10], 50) == 5.0
    assert bench.percentile([0, 10], 100) == 10.0
    assert bench.percentile([0, 10], 0) == 0.0


def test_summarize_empty_and_values():
    empty = bench.summarize([])
    assert empty["n"] == 0 and empty["median"] == 0.0

    s = bench.summarize([100.0, 200.0, 300.0, 400.0])
    assert s["n"] == 4
    assert s["min"] == 100.0 and s["max"] == 400.0
    assert s["median"] == 250.0
    assert s["mean"] == 250.0
    assert s["p95"] >= s["median"]  # p95 never below the median


def test_phrases_cover_both_languages():
    assert set(bench.PHRASES) == {"en", "hi"}
    assert all(bench.PHRASES.values())
