"""Output guardrails. The LLM proposes text; this module decides whether it may be spoken.

Checks
* Every rupee amount / percentage in the reply must match an approved structured knowledge fact.
* Forbidden-claim lexicon (guarantees, testimonials, integrations, availability promises...).
* Identity disclosure present in the greeting.
* No attempt to talk the prospect out of opting out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_AMOUNT_RE = re.compile(r"(?:₹|rs\.?|inr|rupees?|रुपये|रुपए|रु\.?)\s*([0-9][0-9,]*(?:\.\d+)?)|([0-9][0-9,]*(?:\.\d+)?)\s*(?:₹|rs\.?|inr|rupees?|रुपये|रुपए)", re.IGNORECASE)
_PERCENT_RE = re.compile(r"([0-9]{1,3})\s*(?:%|percent|प्रतिशत)", re.IGNORECASE)

_FORBIDDEN = [
    (r"\bguarantee[sd]?\b|\bguaranteed\b|गारंटी", "guarantee"),
    (r"\btestimonial|\bour customers? (say|love)|\bclients? (say|love)|\brated\b|\b5[- ]star", "testimonial"),
    (r"\bintegrat(e|es|ed|ion)s?\b|\bapi\b|\bupi\b|\brazorpay\b|\bwhatsapp\b|\btally\b", "integration"),
    (r"\b(24/7|24x7|round[- ]the[- ]clock)\b|\bdedicated support|\bsupport team\b", "support_commitment"),
    (r"\b(double|triple|increase|boost|grow)\s+(your\s+)?(revenue|income|profit|members?)|\bROI\b", "revenue_claim"),
    (r"\bfree forever\b|\blifetime\b|\bno[- ]cost\b", "pricing_claim"),
    (r"\b(available|launch(es|ing)?)\s+(from|on|in)\s+\w+\s*\d{0,4}", "availability_claim"),
    (r"\b(gst|tax)[- ]?(filing|compliant|compliance)\b", "compliance_feature_claim"),
    (r"\b(biometric|attendance|diet|workout|app for members)\b", "unverified_feature"),
]
_OPT_OUT_PRESSURE = re.compile(r"(but|लेकिन|पर)\s+(just|sirf|bas|only)\s+(one|ek|1)\s+(minute|min|second|sec|मिनट)|don'?t hang up|फोन मत काट", re.IGNORECASE)
_DISCLOSURE = re.compile(r"fitron|फिट्रॉन|फिटरॉन", re.IGNORECASE)
_AUTOMATED = re.compile(r"automated|ai assistant|virtual assistant|voice assistant|स्वचालित|ऑटोमेटेड|एआई सहायक|AI सहायक", re.IGNORECASE)


@dataclass
class GuardrailResult:
    allowed: bool
    violations: list[str] = field(default_factory=list)
    numbers_checked: list[str] = field(default_factory=list)
    safe_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "violations": self.violations, "numbers_checked": self.numbers_checked}


def _approved_numbers(facts: list[dict[str, Any] | None]) -> tuple[set[float], set[float]]:
    amounts: set[float] = set()
    percents: set[float] = set()
    for f in facts:
        if not f:
            continue
        for k, v in f.items():
            if isinstance(v, int | float) and not isinstance(v, bool):
                if "percent" in k:
                    percents.add(float(v))
                elif "inr" in k or "price" in k:
                    amounts.add(float(v))
                    amounts.add(round(float(v)))  # allow rounded (₹999.50 -> ₹1,000)
                    amounts.add(float(round(v / 10.0) * 10))
    return amounts, percents


def check_reply(text: str, *, approved_facts: list[dict[str, Any] | None], state: str, require_disclosure: bool = True, prospect_opted_out: bool = False) -> GuardrailResult:
    res = GuardrailResult(allowed=True)
    amounts, percents = _approved_numbers(approved_facts)
    for m in _AMOUNT_RE.finditer(text):
        raw = (m.group(1) or m.group(2) or "").replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        res.numbers_checked.append(f"₹{raw}")
        if val not in amounts and round(val) not in amounts:
            res.violations.append(f"unapproved amount ₹{raw}")
    for m in _PERCENT_RE.finditer(text):
        val = float(m.group(1))
        res.numbers_checked.append(f"{m.group(1)}%")
        if val not in percents:
            res.violations.append(f"unapproved percentage {m.group(1)}%")
    for pattern, label in _FORBIDDEN:
        if re.search(pattern, text, re.IGNORECASE):
            res.violations.append(f"forbidden claim: {label}")
    if state == "greeting" and require_disclosure:
        if not _DISCLOSURE.search(text):
            res.violations.append("greeting lacks business identity disclosure")
        if not _AUTOMATED.search(text):
            res.violations.append("greeting lacks automated-assistant disclosure")
    if prospect_opted_out and (_OPT_OUT_PRESSURE.search(text) or len(text) > 220):
        res.violations.append("reply continues promotion after opt-out")
    res.allowed = not res.violations
    return res
