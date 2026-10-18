"""Run Alembic migrations programmatically (used at backend startup and by tests)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

REPO_ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS_DIR = REPO_ROOT / "database" / "migrations"


def _config(engine: Engine) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_migrations_dir()))
    cfg.set_main_option("sqlalchemy.url", str(engine.url).replace("%", "%%"))
    cfg.attributes["skip_logging_config"] = True
    return cfg


def _migrations_dir() -> Path:
    if MIGRATIONS_DIR.exists():
        return MIGRATIONS_DIR
    # Frozen (PyInstaller) layout: migrations bundled next to the executable
    import sys

    bundled = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "database" / "migrations"
    if bundled.exists():
        return bundled
    raise FileNotFoundError("Alembic migrations directory not found")


def upgrade(engine: Engine, revision: str = "head") -> None:
    cfg = _config(engine)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, revision)


def downgrade(engine: Engine, revision: str) -> None:
    cfg = _config(engine)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, revision)


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def head_revision() -> str | None:
    return ScriptDirectory.from_config(_config_no_engine()).get_current_head()


def _config_no_engine() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_migrations_dir()))
    return cfg


def is_up_to_date(engine: Engine) -> bool:
    return current_revision(engine) == head_revision()
