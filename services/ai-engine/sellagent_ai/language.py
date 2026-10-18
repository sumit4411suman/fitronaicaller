"""Lightweight Hindi/English detection (Devanagari script + romanised-Hindi lexicon). No network."""

from __future__ import annotations

import re

_ROMAN_HI = {
    "haan", "han", "ji", "nahi", "nahin", "kya", "hai", "hain", "aap", "aapka", "aapke", "hum", "humara", "mujhe", "mera", "meri",
    "kaise", "kitna", "kitne", "paisa", "paise", "rupaye", "rupay", "theek", "thik", "achha", "accha", "bilkul", "abhi", "baad",
    "mein", "main", "kal", "aaj", "samay", "time", "jim", "nahi chahiye", "bataiye", "batao", "sunao", "kar", "karo", "karna",
    "chahiye", "chahie", "matlab", "kyun", "kyon", "kab", "kaun", "kahan", "zaroor", "jarur", "dhanyavaad", "shukriya", "namaste", "namaskar",
}
_EN_HINTS = {"the", "and", "is", "are", "you", "what", "how", "much", "price", "cost", "yes", "no", "please", "thanks", "thank", "not", "interested", "call", "later", "busy"}


def detect(text: str) -> str:
    """Return 'hi', 'en' or 'mixed'. Empty/unknown input returns 'en'."""
    if not text or not text.strip():
        return "en"
    dev = sum(1 for ch in text if "ऀ" <= ch <= "ॿ")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if dev and latin:
        return "mixed" if latin > dev * 0.5 else "hi"
    if dev:
        return "hi"
    words = re.findall(r"[a-z]+", text.lower())
    if not words:
        return "en"
    hi_hits = sum(1 for w in words if w in _ROMAN_HI)
    en_hits = sum(1 for w in words if w in _EN_HINTS)
    if hi_hits and hi_hits >= en_hits and hi_hits / len(words) >= 0.2:
        return "hi" if en_hits == 0 else "mixed"
    return "en"


def resolve(preferred: str, detected: str) -> str:
    """Pick the reply language: manual selection wins; 'auto' follows detection (mixed -> hi)."""
    if preferred in ("hi", "en"):
        return preferred
    return "hi" if detected in ("hi", "mixed") else "en"
