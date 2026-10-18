"""Shared application context handed to every screen."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sellagent_desktop.api_client import ApiClient
from sellagent_desktop.ws_client import WsClient


@dataclass
class AppContext:
    api: ApiClient
    ws: WsClient | None
    data_dir: Path
    backend_url: str
    navigate: Callable[..., None] = lambda key, **kw: None
    notify: Callable[[str, str], None] = lambda text, level="info": None
    settings_cache: dict[str, Any] = field(default_factory=dict)
    health_cache: dict[str, Any] = field(default_factory=dict)
    emergency_stop_active: bool = False
    backend_owned: bool = False
    ai_status: dict[str, Any] = field(default_factory=dict)
    speech_status: dict[str, Any] = field(default_factory=dict)
    devices: list[dict[str, Any]] = field(default_factory=list)
    connected_devices: list[str] = field(default_factory=list)
    last_heartbeat: dict[str, Any] = field(default_factory=dict)  # latest session.heartbeat payload (+ received_at)
