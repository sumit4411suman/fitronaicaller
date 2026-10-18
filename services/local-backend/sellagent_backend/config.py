"""Backend settings. All values can be overridden with ``SELLAGENT_*`` environment variables
or a ``.env`` file inside the data directory. Defaults are the safe, local-only configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "SELL AGENT"
APP_VERSION = "0.1.0"
API_PREFIX = "/api/v1"


def default_data_dir() -> Path:
    if env := os.environ.get("SELLAGENT_DATA_DIR"):
        return Path(env)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "SellAgent"
    return Path.home() / ".local" / "share" / "sellagent"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SELLAGENT_", extra="ignore")

    data_dir: Path = Field(default_factory=default_data_dir)
    db_filename: str = "sellagent.db"
    # Network: localhost only by default. LAN exposure requires explicit opt-in AND a running pairing window.
    host: str = "127.0.0.1"
    port: int = 8765
    lan_enabled: bool = False
    lan_host: str = "0.0.0.0"  # noqa: S104 - only used when lan_enabled is explicitly set by the user
    lan_port: int = 8766
    # Pairing
    pairing_code_ttl_seconds: int = 300
    pairing_max_attempts: int = 5
    device_token_ttl_days: int = 90
    # Calls / safety
    default_calling_mode: str = "human_assisted"
    quiet_hours_start: str = "21:00"  # local time, India default per common practice; configurable
    quiet_hours_end: str = "09:00"
    max_calls_per_hour: int = 10
    max_calls_per_day: int = 50
    min_seconds_between_calls: int = 60
    default_region: str = "IN"
    # Retention (days). 0 = keep forever, handled explicitly in retention job.
    transcript_retention_days: int = 90
    log_retention_days: int = 30
    backup_retention_count: int = 10
    # External connectivity master switch (model downloads, optional providers)
    allow_external_network: bool = False
    # AI providers (local only)
    ollama_base_url: str = "http://127.0.0.1:11434"
    llamacpp_base_url: str = "http://127.0.0.1:8080"
    llm_provider: str = "ollama"  # ollama | llamacpp | none
    llm_model: str = "qwen3:1.7b"
    llm_timeout_seconds: float = 60.0
    whisper_model: str = "small"
    piper_voice_en: str = "en_US-lessac-medium"
    piper_voice_hi: str = ""
    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def local_token_path(self) -> Path:
        return self.data_dir / "local_api_token"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.models_dir, self.backups_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings(**overrides: object) -> Settings:
    """Used by tests to point the backend at a temporary data directory."""
    global _settings
    _settings = Settings(**overrides)  # type: ignore[arg-type]
    return _settings
