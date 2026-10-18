"""Configurable AI sales persona, conversational cue inference and per-call memory.

The persona shapes HOW things are said (name, warmth, length, pacing, wording variety). It can never change WHAT
may be said: approved facts, guardrails, consent, opt-out and emergency stop stay in the state machine and backend.
It always presents itself as an AI assistant and never claims human feelings or consciousness.

Cues are INFERRED from the words the caller used (not from voice tone); they adjust wording only and are never
treated as facts about the person.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

STYLES = ("warm", "concise", "formal")
LENGTHS = ("short", "normal")


@dataclass
class Persona:
    name: str = "Priya"
    gender: str = "female"  # grammatical gender of the persona's Hindi speech
    style: str = "warm"
    response_length: str = "short"
    language_switching: bool = True
    greeting_en: str = ""
    greeting_hi: str = ""
    closing_en: str = ""
    closing_hi: str = ""
    objectives: str = "Understand how the gym manages members and payments; explain approved FITRON facts; offer a demo or a human follow-up."
    memory_turns: int = 8

    def __post_init__(self) -> None:
        self.name = (self.name or "Priya").strip()[:40]
        self.gender = self.gender if self.gender in ("female", "male") else "female"
        self.style = self.style if self.style in STYLES else "warm"
        self.response_length = self.response_length if self.response_length in LENGTHS else "short"
        self.memory_turns = max(2, min(30, int(self.memory_turns or 8)))

    def greeting(self, lang: str, *, contact_person: str, business_name: str) -> str | None:
        """Custom greeting, always forced to include the AI disclosure; None = use the approved default."""
        tpl = self.greeting_hi if lang == "hi" else self.greeting_en
        if not tpl.strip():
            return None
        try:
            text = tpl.format(name=self.name, contact_person=contact_person, business_name=business_name)
        except (KeyError, IndexError, ValueError):
            text = tpl
        if not re.search(r"\bAI\b|स्वचालित|automated", text, re.IGNORECASE):
            text = (f"मैं {self.name}, FITRON की AI सहायक हूँ। " if lang == "hi" else f"I'm {self.name}, an AI assistant for FITRON. ") + text
        return text

    def llm_style(self, lang: str) -> str:
        tone = {"warm": "warm, friendly and respectful", "concise": "brief and to the point", "formal": "polite and formal"}[self.style]
        length = "one short sentence, at most two" if self.response_length == "short" else "at most two or three short sentences"
        return (
            f"You are {self.name}, an AI sales assistant (not a human) for FITRON. Speak in a {tone} way, using natural Indian "
            f"{'Hindi' if lang == 'hi' else 'English'} phrasing, with {length}. Acknowledge what the gym owner said before answering. "
            "Never claim to be human or to have feelings. "
            f"Objectives: {self.objectives}"
        )


# --------------------------------------------------------------------------------------------- cues
CUE_PATTERNS: dict[str, tuple[str, ...]] = {
    "busy": ("busy", "in a meeting", "driving", "not a good time", "no time", "abhi time nahi", "time nahi hai", "व्यस्त", "समय नहीं", "बाद में", "baad mein", "later"),
    "confused": ("didn't understand", "did not understand", "don't understand", "what do you mean", "samajh nahi", "samjha nahi", "समझ नहीं", "matlab", "मतलब", "kya bola", "pardon", "come again"),
    "price_concern": ("expensive", "costly", "too much", "mehenga", "mahanga", "महंगा", "budget", "discount", "kam karo", "price", "kitna", "कितना", "कीमत"),
    "existing_software": ("already use", "already have", "we use", "using software", "tally", "excel", "spreadsheet", "pehle se", "पहले से", "software hai", "app use"),
    "interest": ("interesting", "sounds good", "tell me more", "aur batao", "और बताइए", "achha hai", "accha", "demo", "dikhao", "show me"),
    "hesitation": ("not sure", "maybe", "let me think", "sochta", "soch ke", "सोच", "pata nahi", "पता नहीं", "dekhte hain"),
    "impatient": ("quickly", "jaldi", "जल्दी", "come to the point", "seedha bolo", "short me", "just tell me"),
    "end_call": ("bye", "goodbye", "rakhta hoon", "rakhti hoon", "phone rakh", "ok bye", "thank you bye", "चलिए", "नमस्ते रखता"),
    "clarification": ("repeat", "say again", "dobara", "दोबारा", "phir se", "फिर से", "one more time"),
}


def infer_cues(text: str) -> set[str]:
    t = (text or "").lower()
    return {cue for cue, pats in CUE_PATTERNS.items() if any(p in t for p in pats)}


# --------------------------------------------------------------------------------------------- memory
SOFTWARE_NAMES = ("tally", "excel", "spreadsheet", "google sheets", "zoho", "busy", "vyapar", "khatabook", "register", "paper", "notebook", "diary")
NEEDS = {
    "membership management": ("member", "membership", "renewal", "मेंबर", "सदस्य"),
    "payment tracking": ("payment", "fees", "dues", "collection", "pending", "पेमेंट", "फीस", "बकाया"),
    "gym accounting": ("account", "accounting", "hisab", "hisaab", "हिसाब", "gst", "expense", "profit"),
}


@dataclass
class ConversationMemory:
    """Context of the CURRENT call only, rebuilt from its transcript. Nothing persists across calls."""

    turns: list[tuple[str, str]] = field(default_factory=list)  # (speaker, text), oldest first
    current_tool: str | None = None
    needs: list[str] = field(default_factory=list)
    cues_seen: list[str] = field(default_factory=list)
    last_agent: str = ""

    @classmethod
    def from_turns(cls, turns: list[tuple[str, str]], limit: int = 8) -> ConversationMemory:
        m = cls()
        for speaker, text in turns:
            m.observe(speaker, text)
        m.turns = m.turns[-2 * limit :]
        return m

    def observe(self, speaker: str, text: str) -> set[str]:
        text = (text or "").strip()
        if not text:
            return set()
        self.turns.append((speaker, text))
        if speaker == "agent":
            self.last_agent = text
            return set()
        low = text.lower()
        for name in SOFTWARE_NAMES:
            if name in low and self.current_tool is None:
                self.current_tool = name
        for need, words in NEEDS.items():
            if need not in self.needs and any(w in low for w in words):
                self.needs.append(need)
        cues = infer_cues(text)
        self.cues_seen.extend(sorted(cues))
        return cues

    def summary(self) -> str:
        parts = []
        if self.current_tool:
            parts.append(f"currently uses: {self.current_tool}")
        if self.needs:
            parts.append("interested in: " + ", ".join(self.needs))
        return "; ".join(parts) or "nothing captured yet"

    def history_block(self, limit: int = 8) -> str:
        return "\n".join(f"{'AI' if s == 'agent' else 'Gym owner'}: {t}" for s, t in self.turns[-2 * limit :])
