"""Typed application settings persisted in the ``settings`` table, with guarded keys.

The autonomous-calling switch is special: it can only be turned on when the release gate
(``release_gate.autonomous_calling_allowed``) is satisfied by real-device audio evidence.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.db.models import Setting
from sellagent_backend.services import audit

DEFAULTS: dict[str, Any] = {
    "general.app_display_name": "SELL AGENT",
    "general.business_name": "FITRON",
    "general.operator_name": "Operator",
    "general.locale": "en-IN",
    "general.timezone": "Asia/Kolkata",
    "privacy.allow_external_network": False,
    "privacy.telemetry": False,
    "privacy.record_calls": False,
    "privacy.transcript_retention_days": 90,
    "privacy.log_retention_days": 30,
    "privacy.recording_disclosure_text": "This call may be assisted by an automated system.",
    "calling.default_mode": "human_assisted",
    "calling.autonomous_enabled": False,
    "calling.quiet_hours_start": "21:00",
    "calling.quiet_hours_end": "10:00",
    "calling.max_calls_per_hour": 10,
    "calling.max_calls_per_day": 50,
    "calling.min_seconds_between_calls": 60,
    "calling.require_consent": True,
    "calling.emergency_stop_active": False,
    "calling.identity_disclosure_required": True,
    "network.lan_pairing_enabled": False,
    "ai.llm_provider": "ollama",
    "ai.llm_model": "qwen3:1.7b",
    "ai.whisper_model": "base",
    "ai.piper_voice_en": "en_US-lessac-medium",
    "ai.piper_voice_hi": "",
    "ai.language": "auto",
    "ai.vad_engine": "auto",
    "ai.tts_speed_percent": 100,
    "persona.enabled": True,
    "persona.name": "Priya",
    "persona.gender": "female",
    "persona.style": "warm",
    "persona.response_length": "short",
    "persona.language_switching": True,
    "persona.default_language": "auto",
    "persona.greeting_en": "",
    "persona.greeting_hi": "",
    "persona.closing_en": "",
    "persona.closing_hi": "",
    "persona.objectives": "Understand how the gym manages members and payments; explain approved FITRON facts; offer a demo or a human follow-up.",
    "persona.memory_turns": 8,
    "persona.voice_en": "",
    "persona.voice_hi": "",
    "persona.pause_ms": 250,
    "persona.volume_percent": 100,
    "persona.barge_in": True,
    "persona.handoff": "callback",
    "ai.piper_executable": "",
    "privacy.allow_live_transcription": False,
    "workers.campaign_engine_enabled": True,
    "workers.max_open_jobs_per_campaign": 3,
    "followups.auto_create": True,
    "followups.default_after_days": 2,
    "followups.remind_minutes_before": 15,
    "reports.daily_enabled": True,
    "reports.daily_at": "21:05",
    "backup.encrypt": True,
    "backup.retention_count": 10,
    "release_gate.autonomous_calling_allowed": False,
    "release_gate.evidence": None,
    # External audio gateway (calling Approach C): an independently qualified route plugged into the media-gateway
    # adapter. OFF by default; turning it on never bypasses the release gate - real-device evidence is still required.
    "gateway.enabled": False,
    "gateway.kind": "sip",  # sip | gateway_phone
    "gateway.bind_host": "127.0.0.1",  # loopback only; must never be a LAN/0.0.0.0 address
    "gateway.sip_host": "127.0.0.1",
    "gateway.sip_port": 5060,
    "gateway.audiosocket_port": 9092,  # Asterisk app_audiosocket connects here (loopback) to bridge call audio
    "gateway.codec": "g722",  # g722 | pcmu | pcma
    "gateway.caller_id": "",  # the verified calling identity the gateway presents (E.164); informational
}

READ_ONLY_KEYS = {"release_gate.autonomous_calling_allowed", "release_gate.evidence"}


class SettingsError(ValueError):
    pass


def get(session: Session, key: str) -> Any:
    row = session.get(Setting, key)
    if row is None:
        if key not in DEFAULTS:
            raise KeyError(key)
        return DEFAULTS[key]
    return row.value


def get_all(session: Session) -> dict[str, Any]:
    out = dict(DEFAULTS)
    for row in session.scalars(select(Setting)):
        out[row.key] = row.value
    return out


def _coerce(key: str, value: Any) -> Any:
    default = DEFAULTS.get(key)
    if default is None:
        return value
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false", "1", "0", "yes", "no"}:
            return value.lower() in {"true", "1", "yes"}
        raise SettingsError(f"{key} expects a boolean")
    if isinstance(default, int):
        try:
            iv = int(value)
        except (TypeError, ValueError) as exc:
            raise SettingsError(f"{key} expects an integer") from exc
        if iv < 0:
            raise SettingsError(f"{key} must be >= 0")
        return iv
    if isinstance(default, str):
        if not isinstance(value, str):
            raise SettingsError(f"{key} expects a string")
        if key.endswith(("quiet_hours_start", "quiet_hours_end", "daily_at")):
            parts = value.split(":")
            if len(parts) != 2 or not all(p.isdigit() for p in parts) or not (0 <= int(parts[0]) < 24 and 0 <= int(parts[1]) < 60):
                raise SettingsError(f"{key} must be HH:MM")
        return value
    return value


def set_value(session: Session, key: str, value: Any, *, actor: str = "operator", force_internal: bool = False) -> Any:
    if key not in DEFAULTS:
        raise SettingsError(f"unknown setting {key!r}")
    if key in READ_ONLY_KEYS and not force_internal:
        raise SettingsError(f"{key} is set by the release gate, not by the user")
    value = _coerce(key, value)
    if key == "calling.autonomous_enabled" and value is True and not get(session, "release_gate.autonomous_calling_allowed"):
        raise SettingsError(
            "Autonomous calling is disabled by the release gate: real-device tests must demonstrate both "
            "remote-audio capture and AI-speech transmission through supported interfaces first."
        )
    if key == "calling.default_mode" and value not in {"human_assisted", "autonomous"}:
        raise SettingsError("calling.default_mode must be human_assisted or autonomous")
    choices = {"persona.gender": {"female", "male"}, "persona.style": {"warm", "concise", "formal"}, "persona.response_length": {"short", "normal"},
               "persona.default_language": {"auto", "hi", "en"}, "persona.handoff": {"callback", "operator"},
               "gateway.kind": {"sip", "gateway_phone"}, "gateway.codec": {"g722", "pcmu", "pcma"}}
    if key in choices and value not in choices[key]:
        raise SettingsError(f"{key} must be one of {', '.join(sorted(choices[key]))}")
    if key == "gateway.bind_host" and value not in {"127.0.0.1", "::1", "localhost"}:
        raise SettingsError("gateway.bind_host must be loopback (127.0.0.1, ::1 or localhost): the audio gateway is never exposed on the network")
    if key in ("gateway.sip_port", "gateway.audiosocket_port") and not 1 <= value <= 65535:
        raise SettingsError(f"{key} must be a valid port (1-65535)")
    if key == "persona.name" and not (1 <= len(value.strip()) <= 40):
        raise SettingsError("persona.name must be 1-40 characters")
    if key in ("persona.greeting_en", "persona.greeting_hi", "persona.closing_en", "persona.closing_hi", "persona.objectives") and len(value) > 500:
        raise SettingsError(f"{key} is limited to 500 characters")
    if key == "persona.memory_turns" and not 2 <= value <= 30:
        raise SettingsError("persona.memory_turns must be between 2 and 30")
    if key == "persona.pause_ms" and value > 1500:
        raise SettingsError("persona.pause_ms must be at most 1500")
    if key == "persona.volume_percent" and not 20 <= value <= 150:
        raise SettingsError("persona.volume_percent must be between 20 and 150")
    if key == "ai.tts_speed_percent" and not 50 <= value <= 200:
        raise SettingsError("ai.tts_speed_percent must be between 50 and 200")
    if key == "ai.vad_engine" and value not in {"auto", "silero", "energy"}:
        raise SettingsError("ai.vad_engine must be auto, silero or energy")
    if key == "ai.llm_provider" and value not in {"ollama", "llamacpp", "none"}:
        raise SettingsError("ai.llm_provider must be ollama, llamacpp or none")
    row = session.get(Setting, key)
    old = row.value if row else DEFAULTS[key]
    if row is None:
        row = Setting(key=key, value=value, updated_by=actor)
        session.add(row)
    else:
        row.value = value
        row.updated_by = actor
    session.flush()
    audit.record(session, "settings.update", actor=actor, entity_type="setting", entity_id=key, data={"old": old, "new": value})
    return value


def set_release_gate(session: Session, allowed: bool, evidence: dict[str, Any] | None, *, actor: str = "system") -> None:
    set_value(session, "release_gate.autonomous_calling_allowed", allowed, actor=actor, force_internal=True)
    set_value(session, "release_gate.evidence", evidence, actor=actor, force_internal=True)
    if not allowed and get(session, "calling.autonomous_enabled"):
        set_value(session, "calling.autonomous_enabled", False, actor=actor)
