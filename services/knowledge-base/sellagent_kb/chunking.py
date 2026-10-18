from __future__ import annotations

import re

_SENT_SPLIT = re.compile(r"(?<=[.!?।])\s+")


def estimate_tokens(text: str) -> int:
    # Rough: ~4 chars/token for Latin, ~2 chars/token for Devanagari-heavy text
    dev = sum(1 for ch in text if "ऀ" <= ch <= "ॿ")
    return max(1, int((len(text) - dev) / 4 + dev / 2))


def chunk_text(text: str, *, max_tokens: int = 160, overlap_sentences: int = 1) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    sentences = [s for s in _SENT_SPLIT.split(text) if s]
    chunks: list[str] = []
    cur: list[str] = []
    for s in sentences:
        cand = " ".join([*cur, s])
        if cur and estimate_tokens(cand) > max_tokens:
            chunks.append(" ".join(cur))
            cur = cur[-overlap_sentences:] if overlap_sentences else []
        cur.append(s)
    if cur:
        chunks.append(" ".join(cur))
    return chunks
