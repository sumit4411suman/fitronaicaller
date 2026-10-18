"""Backup & restore using SQLite's online backup API (consistent even under WAL), optional
AES-GCM encryption with a passphrase (scrypt KDF), retention and integrity verification."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import struct
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"SAGBK1"  # SELL AGENT backup v1
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**15, 8, 1


class BackupError(RuntimeError):
    pass


def _derive(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P).derive(passphrase.encode("utf-8"))


def encrypt_bytes(data: bytes, passphrase: str, meta: dict[str, Any]) -> bytes:
    if len(passphrase) < 8:
        raise BackupError("passphrase must be at least 8 characters")
    salt, nonce = os.urandom(16), os.urandom(12)
    header = json.dumps(meta, sort_keys=True).encode("utf-8")
    ct = AESGCM(_derive(passphrase, salt)).encrypt(nonce, data, header)
    return MAGIC + struct.pack(">I", len(header)) + header + salt + nonce + ct


def decrypt_bytes(blob: bytes, passphrase: str) -> tuple[bytes, dict[str, Any]]:
    if not blob.startswith(MAGIC):
        raise BackupError("not an encrypted SELL AGENT backup")
    off = len(MAGIC)
    (hlen,) = struct.unpack(">I", blob[off : off + 4])
    off += 4
    header = blob[off : off + hlen]
    off += hlen
    salt, nonce, ct = blob[off : off + 16], blob[off + 16 : off + 28], blob[off + 28 :]
    try:
        data = AESGCM(_derive(passphrase, salt)).decrypt(nonce, ct, header)
    except InvalidTag as exc:
        raise BackupError("wrong passphrase or corrupted backup") from exc
    return data, json.loads(header)


def _snapshot(db_path: Path) -> bytes:
    src = sqlite3.connect(db_path)
    try:
        mem = sqlite3.connect(":memory:")
        src.backup(mem)
        src.close()
        tmp = db_path.parent / f".snapshot-{os.getpid()}.db"
        disk = sqlite3.connect(tmp)
        mem.backup(disk)
        disk.close()
        mem.close()
        data = tmp.read_bytes()
        tmp.unlink(missing_ok=True)
        return data
    finally:
        try:
            src.close()
        except sqlite3.ProgrammingError:
            pass


def create_backup(db_path: Path, backups_dir: Path, *, passphrase: str | None, app_version: str, keep: int = 10) -> dict[str, Any]:
    backups_dir.mkdir(parents=True, exist_ok=True)
    data = _snapshot(db_path)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    meta = {"created_at": ts, "app_version": app_version, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "encrypted": bool(passphrase)}
    if passphrase:
        out = backups_dir / f"sellagent-{ts}.sabk"
        out.write_bytes(encrypt_bytes(data, passphrase, meta))
    else:
        out = backups_dir / f"sellagent-{ts}.db"
        out.write_bytes(data)
        (backups_dir / f"sellagent-{ts}.json").write_text(json.dumps(meta, indent=2))
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    _prune(backups_dir, keep)
    return {"path": str(out), **meta}


def _prune(backups_dir: Path, keep: int) -> None:
    files = sorted([p for p in backups_dir.iterdir() if p.suffix in (".sabk", ".db")], key=lambda p: p.name)
    for p in files[:-keep] if keep > 0 else []:
        p.unlink(missing_ok=True)
        p.with_suffix(".json").unlink(missing_ok=True)


def list_backups(backups_dir: Path) -> list[dict[str, Any]]:
    out = []
    if not backups_dir.exists():
        return out
    for p in sorted(backups_dir.iterdir(), reverse=True):
        if p.suffix == ".sabk":
            out.append({"path": str(p), "name": p.name, "encrypted": True, "size": p.stat().st_size})
        elif p.suffix == ".db":
            meta_p = p.with_suffix(".json")
            meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
            out.append({"path": str(p), "name": p.name, "encrypted": False, "size": p.stat().st_size, **meta})
    return out


def verify_backup(path: Path, passphrase: str | None = None) -> dict[str, Any]:
    blob = path.read_bytes()
    if path.suffix == ".sabk":
        if not passphrase:
            raise BackupError("passphrase required")
        data, meta = decrypt_bytes(blob, passphrase)
    else:
        data = blob
        meta_p = path.with_suffix(".json")
        meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    digest = hashlib.sha256(data).hexdigest()
    if meta.get("sha256") and meta["sha256"] != digest:
        raise BackupError("checksum mismatch")
    tmp = path.parent / f".verify-{os.getpid()}.db"
    tmp.write_bytes(data)
    try:
        conn = sqlite3.connect(tmp)
        ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tables = [r[0] for r in conn.execute("select name from sqlite_master where type='table'")]
        conn.close()
    finally:
        tmp.unlink(missing_ok=True)
    if ok != "ok":
        raise BackupError(f"integrity check failed: {ok}")
    return {"ok": True, "sha256": digest, "tables": tables, **meta}


def restore_backup(path: Path, db_path: Path, *, passphrase: str | None = None) -> dict[str, Any]:
    """Verify, then atomically replace the live database. Caller must dispose all engines first
    and re-run migrations afterwards. A pre-restore safety copy is written next to the DB."""
    info = verify_backup(path, passphrase)
    blob = path.read_bytes()
    data = decrypt_bytes(blob, passphrase or "")[0] if path.suffix == ".sabk" else blob
    if db_path.exists():
        safety = db_path.with_name(db_path.stem + f".pre-restore-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.db")
        safety.write_bytes(_snapshot(db_path))
        info["pre_restore_copy"] = str(safety)
    for suffix in ("-wal", "-shm"):
        Path(str(db_path) + suffix).unlink(missing_ok=True)
    tmp = db_path.with_suffix(".restoring")
    tmp.write_bytes(data)
    os.replace(tmp, db_path)
    return info
