"""The 'Run Priya over Bluetooth' runner's offline checks: its selftest (Priya's conversation brain:
AI disclosure, approved-price-only, Hindi switch, opt-out) and that only APPROVED FITRON facts are loaded.
Headless - no audio, no models, no phone."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_priya_bluetooth.py"
_spec = importlib.util.spec_from_file_location("run_priya_bluetooth", _SCRIPT)
assert _spec and _spec.loader
rpb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rpb)


def test_selftest_passes():
    assert rpb.selftest() == 0


def test_only_approved_facts_loaded():
    facts = rpb.approved_fitron_facts()
    blob = " ".join(f.text for f in facts)
    assert "₹1,999" in blob  # approved price present
    # the unapproved first-100 launch offer must NOT be exposed
    assert "first 100" not in blob.lower() and "₹1,000" not in blob and "50%" not in blob
