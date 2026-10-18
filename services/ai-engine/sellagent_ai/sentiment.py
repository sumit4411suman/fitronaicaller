"""Lightweight, offline Hindi/English (incl. romanised Hindi) sentiment for call turns.

Lexicon-based with negation handling. It is an indicator for the operator and the call summary, never an input to
eligibility, consent or opt-out decisions. Returns 'positive' | 'neutral' | 'negative' and a score in [-1, 1].
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_POS = {
    # English
    "yes", "sure", "great", "good", "interested", "interesting", "nice", "ok", "okay", "fine", "perfect", "helpful", "useful",
    "love", "like", "want", "need", "excellent", "awesome", "thanks", "thank", "definitely", "please", "demo", "send",
    # romanised Hindi
    "haan", "han", "ji", "achha", "accha", "badhiya", "bahut", "zaroor", "jarur", "bilkul", "theek", "thik", "pasand", "chahiye",
    "shukriya", "dhanyavaad", "sahi", "mast",
    # Devanagari
    "हाँ", "हां", "जी", "अच्छा", "बढ़िया", "ज़रूर", "जरूर", "बिल्कुल", "ठीक", "पसंद", "चाहिए", "धन्यवाद", "शुक्रिया", "सही",
}
_NEG = {
    "no", "not", "never", "busy", "expensive", "costly", "bad", "useless", "waste", "angry", "stop", "annoying", "spam",
    "irritating", "problem", "complaint", "worst", "hate", "remove", "disturb", "later",
    "nahi", "nahin", "mat", "mehenga", "mahanga", "bekar", "faltu", "pareshan", "band", "galat", "bakwas",
    "नहीं", "मत", "महंगा", "बेकार", "फालतू", "परेशान", "बंद", "गलत", "बकवास", "व्यस्त",
}
_NEGATORS = {"not", "no", "never", "nahi", "nahin", "mat", "नहीं", "मत", "na", "ना"}
_STRONG_NEG = re.compile(r"(do ?n[o']?t call|stop calling|remove my number|call mat|mat karo|नहीं चाहिए|कॉल मत|फोन मत|spam)", re.I)


@dataclass
class Sentiment:
    label: str
    score: float
    hits: dict[str, int]


def analyze(text: str) -> Sentiment:
    if not text or not text.strip():
        return Sentiment("neutral", 0.0, {"positive": 0, "negative": 0})
    if _STRONG_NEG.search(text):
        return Sentiment("negative", -1.0, {"positive": 0, "negative": 1})
    tokens = re.findall(r"[\wऀ-ॿ]+", text.lower())
    pos = neg = 0
    for i, t in enumerate(tokens):
        negated = i > 0 and tokens[i - 1] in _NEGATORS
        if t in _POS and t not in _NEGATORS:
            if negated:
                neg += 1
            else:
                pos += 1
        elif t in _NEG and t not in _NEGATORS:
            neg += 1
        elif t in _NEGATORS and (i + 1 >= len(tokens)):
            neg += 1
    total = pos + neg
    score = 0.0 if total == 0 else (pos - neg) / total
    label = "positive" if score > 0.2 else "negative" if score < -0.2 else "neutral"
    return Sentiment(label, round(score, 2), {"positive": pos, "negative": neg})


def overall(labels: list[str | None]) -> str | None:
    vals = [{"positive": 1, "neutral": 0, "negative": -1}[x] for x in labels if x in ("positive", "neutral", "negative")]
    if not vals:
        return None
    avg = sum(vals) / len(vals)
    return "positive" if avg > 0.25 else "negative" if avg < -0.25 else "neutral"
