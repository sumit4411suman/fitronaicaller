"""Telecom adapters. Each adapter declares what it can *prove* it supports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class RouteCapabilities:
    route: str
    can_dial: bool
    reports_call_state: bool
    remote_audio_capture: bool
    audio_injection: bool
    autonomous_supported: bool
    notes: list[str] = field(default_factory=list)


class TelecomAdapter(Protocol):
    route: str

    def capabilities(self) -> RouteCapabilities: ...

    async def dial(self, *, call_job_id: str, e164: str, display_name: str | None, mode: str, authorization_token: str, language: str, device_id: str | None) -> tuple[bool, str]: ...

    async def cancel(self, *, call_job_id: str, device_id: str | None, reason: str) -> bool: ...
