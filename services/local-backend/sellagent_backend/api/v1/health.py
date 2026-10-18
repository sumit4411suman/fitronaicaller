from __future__ import annotations

import platform
import shutil
import sys
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_local_auth
from sellagent_backend.config import APP_NAME, APP_VERSION
from sellagent_backend.db import migrate
from sellagent_backend.security.secret_store import protection_mode
from sellagent_protocol import PROTOCOL_VERSION

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/ping")
def ping() -> dict:
    """Unauthenticated liveness probe (returns no sensitive data)."""
    return {"ok": True, "app": APP_NAME, "version": APP_VERSION, "protocol_version": PROTOCOL_VERSION}


@router.get("", dependencies=[Depends(require_local_auth)])
def health(request: Request, db: Session = Depends(get_db)) -> dict:
    st = request.app.state
    db_ok = db.execute(text("select 1")).scalar() == 1
    journal = db.execute(text("PRAGMA journal_mode")).scalar()
    fk = db.execute(text("PRAGMA foreign_keys")).scalar()
    fts = db.execute(text("select count(*) from sqlite_master where name='knowledge_chunks_fts'")).scalar()
    disk = shutil.disk_usage(st.settings.data_dir)
    mem_total = None
    try:
        import psutil  # type: ignore

        mem_total = psutil.virtual_memory().total
    except ImportError:
        pass
    return {
        "ok": db_ok, "app": APP_NAME, "version": APP_VERSION, "protocol_version": PROTOCOL_VERSION, "python": sys.version.split()[0],
        "platform": platform.platform(), "started_at": st.started_at, "uptime_seconds": (datetime.now(UTC) - st.started_at).total_seconds(),
        "database": {"path": str(st.settings.db_path), "journal_mode": journal, "foreign_keys": bool(fk), "fts5": bool(fts), "revision": migrate.current_revision(st.engine), "head": migrate.head_revision(), "up_to_date": migrate.is_up_to_date(st.engine)},
        "disk": {"total": disk.total, "free": disk.free}, "ram_total": mem_total, "secret_protection": protection_mode(),
        "bind": {"host": st.settings.host, "port": st.settings.port}, "lan": st.lan.status() if getattr(st, "lan", None) else {"enabled": False},
        "connected_devices": st.hub.connected_devices(), "external_network_allowed": bool(st.settings.allow_external_network),
    }
