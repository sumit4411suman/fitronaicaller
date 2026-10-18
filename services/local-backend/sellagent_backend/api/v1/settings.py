from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_local_auth
from sellagent_backend.api.schemas import BackupIn, RestoreIn, SettingPatch
from sellagent_backend.api.v1.errors import bad_request
from sellagent_backend.config import APP_VERSION
from sellagent_backend.services import audit, backup, settings_service
from sellagent_backend.services.settings_service import DEFAULTS, READ_ONLY_KEYS, SettingsError
from sellagent_backend.telecom import audio_gate_status

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_local_auth)])
backup_router = APIRouter(prefix="/backup", tags=["backup"], dependencies=[Depends(require_local_auth)])


@router.get("")
def get_settings(db: Session = Depends(get_db)) -> dict:
    return {"values": settings_service.get_all(db), "defaults": DEFAULTS, "read_only": sorted(READ_ONLY_KEYS)}


@router.patch("")
def patch_settings(body: SettingPatch, request: Request, db: Session = Depends(get_db)) -> dict:
    applied: dict = {}
    for k, v in body.values.items():
        try:
            applied[k] = settings_service.set_value(db, k, v)
        except SettingsError as exc:
            db.rollback()
            raise bad_request(str(exc), code="settings_error") from exc
    if "network.lan_pairing_enabled" in applied:
        request.app.state.lan_requested = bool(applied["network.lan_pairing_enabled"])
    return {"applied": applied}


@router.get("/release-gate")
def release_gate(db: Session = Depends(get_db)) -> dict:
    gate = audio_gate_status(db)
    return {**gate, "setting": settings_service.get(db, "release_gate.autonomous_calling_allowed"), "autonomous_enabled": settings_service.get(db, "calling.autonomous_enabled"), "explanation": "Autonomous cellular AI calling stays disabled until operator-confirmed real-device tests PASS for BOTH remote-audio capture (inbound) and AI-speech transmission (outbound) through supported Android interfaces."}


@router.post("/release-gate/recompute")
def recompute_gate(db: Session = Depends(get_db)) -> dict:
    gate = audio_gate_status(db)
    settings_service.set_release_gate(db, gate["allowed"], gate["evidence"])
    return gate


@router.post("/retention/run")
def run_retention(db: Session = Depends(get_db)) -> dict:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import delete

    from sellagent_backend.db.models import Transcript

    days = int(settings_service.get(db, "privacy.transcript_retention_days"))
    removed = 0
    if days > 0:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        removed = db.execute(delete(Transcript).where(Transcript.created_at < cutoff)).rowcount or 0
    audit.record(db, "retention.run", data={"transcripts_removed": removed, "days": days})
    return {"transcripts_removed": removed, "retention_days": days}


@backup_router.get("")
def list_backups(request: Request) -> list[dict]:
    return backup.list_backups(request.app.state.settings.backups_dir)


@backup_router.post("")
def create_backup(body: BackupIn, request: Request, db: Session = Depends(get_db)) -> dict:
    s = request.app.state.settings
    if settings_service.get(db, "backup.encrypt") and not body.passphrase:
        raise bad_request("backup encryption is enabled; provide a passphrase (>= 8 chars) or disable backup.encrypt", code="passphrase_required")
    db.commit()
    try:
        info = backup.create_backup(s.db_path, s.backups_dir, passphrase=body.passphrase, app_version=APP_VERSION, keep=int(settings_service.get(db, "backup.retention_count")))
    except backup.BackupError as exc:
        raise bad_request(str(exc)) from exc
    audit.record(db, "backup.create", data={"path": info["path"], "encrypted": info["encrypted"], "sha256": info["sha256"]})
    return info


@backup_router.post("/verify")
def verify(body: RestoreIn, request: Request) -> dict:
    from pathlib import Path

    p = Path(body.path)
    if not p.is_absolute() or p.resolve().parent != request.app.state.settings.backups_dir.resolve():
        raise bad_request("path must be a file inside the backups directory", code="path_rejected")
    try:
        return backup.verify_backup(p, body.passphrase)
    except backup.BackupError as exc:
        raise bad_request(str(exc)) from exc


@backup_router.post("/restore")
def restore(body: RestoreIn, request: Request, db: Session = Depends(get_db)) -> dict:
    from pathlib import Path

    s = request.app.state.settings
    p = Path(body.path)
    if not p.is_absolute() or p.resolve().parent != s.backups_dir.resolve():
        raise bad_request("path must be a file inside the backups directory", code="path_rejected")
    audit.record(db, "backup.restore.start", severity="critical", data={"path": str(p)})
    db.commit()
    db.close()
    request.app.state.engine.dispose()
    try:
        info = backup.restore_backup(p, s.db_path, passphrase=body.passphrase)
    except backup.BackupError as exc:
        raise bad_request(str(exc)) from exc
    from sellagent_backend.db import migrate

    migrate.upgrade(request.app.state.engine)
    return {**info, "restart_recommended": True}
