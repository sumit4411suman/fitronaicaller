"""Builds the configured AI sales persona and per-call memory for the conversation engine.

Persona settings change wording, voice and pacing only. Approved facts, guardrails, consent, opt-out and emergency
stop are enforced elsewhere and cannot be changed from here.
"""

from __future__ import annotations

from typing import Any

from sellagent_ai.persona import ConversationMemory, Persona
from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.db.models import Transcript
from sellagent_backend.services import settings_service


def load_persona(s: Session) -> Persona | None:
    if not settings_service.get(s, "persona.enabled"):
        return None
    g = lambda k: settings_service.get(s, f"persona.{k}")  # noqa: E731
    return Persona(
        name=g("name"), gender=g("gender"), style=g("style"), response_length=g("response_length"), language_switching=bool(g("language_switching")),
        greeting_en=g("greeting_en"), greeting_hi=g("greeting_hi"), closing_en=g("closing_en"), closing_hi=g("closing_hi"),
        objectives=g("objectives"), memory_turns=int(g("memory_turns")),
    )


def call_memory(s: Session, call_id: str, limit: int) -> ConversationMemory:
    rows = list(s.scalars(select(Transcript).where(Transcript.call_id == call_id, Transcript.speaker.in_(("prospect", "agent"))).order_by(Transcript.seq)))
    return ConversationMemory.from_turns([(r.speaker, r.text) for r in rows], limit=limit)


def voices(s: Session) -> dict[str, str]:
    """Persona voices override the generic Piper voices when set."""
    return {lang: settings_service.get(s, f"persona.voice_{lang}") or settings_service.get(s, f"ai.piper_voice_{lang}") for lang in ("en", "hi")}


def tts_options(s: Session) -> dict[str, Any]:
    return {
        "speed": max(50, min(200, int(settings_service.get(s, "ai.tts_speed_percent")))) / 100,
        "volume": int(settings_service.get(s, "persona.volume_percent")) / 100 if settings_service.get(s, "persona.enabled") else 1.0,
        "pause_ms": int(settings_service.get(s, "persona.pause_ms")) if settings_service.get(s, "persona.enabled") else 0,
    }


def effective_language(s: Session, requested: str, persona: Persona | None) -> str:
    """'auto' lets the engine follow the caller; with switching off the persona keeps its default language."""
    if requested in ("hi", "en"):
        return requested
    if persona is not None and not persona.language_switching:
        default = settings_service.get(s, "persona.default_language")
        if default in ("hi", "en"):
            return default
        ai = settings_service.get(s, "ai.language")
        return ai if ai in ("hi", "en") else "en"
    return requested
