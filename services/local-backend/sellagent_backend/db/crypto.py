"""At-rest encryption of the local SQLite database with SQLCipher (AES-256, page-level).

* The 256-bit key is random, generated on first run and stored in ``<data dir>/db_key`` protected with
  Windows DPAPI (current user) or 0600 permissions elsewhere (see ``security/secret_store.py``).
* ``sqlcipher3-wheels`` ships prebuilt SQLCipher for Windows x64 / Python 3.12 with FTS5.
* A database created by an earlier, unencrypted release is converted in place on first start
  (``sqlcipher_export``), verified, and the plaintext file is removed.
* If SQLCipher is not installed the database stays plaintext and ``/health`` reports
  ``encryption: unavailable``; ``SELLAGENT_DB_ENCRYPTION=off`` disables it explicitly.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from sellagent_backend.security.secret_store import read_secret_file, write_secret_file

PLAINTEXT_HEADER = b"SQLite format 3\x00"

try:  # pragma: no cover - import guard
    import sqlcipher3.dbapi2 as _sqlcipher  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    _sqlcipher = None


def available() -> bool:
    return _sqlcipher is not None and os.environ.get("SELLAGENT_DB_ENCRYPTION", "on").lower() not in ("off", "0", "false")


def dbapi() -> Any:
    return _sqlcipher if available() else sqlite3


def key_path(data_dir: Path) -> Path:
    return data_dir / "db_key"


def get_or_create_key(data_dir: Path) -> str | None:
    if not available():
        return None
    p = key_path(data_dir)
    key = read_secret_file(p)
    if not key:
        key = secrets.token_hex(32)
        write_secret_file(p, key)
    return key


def _key_pragma(key: str) -> str:
    if not all(c in "0123456789abcdef" for c in key) or len(key) != 64:
        raise ValueError("database key must be 64 lowercase hex characters")
    return f"PRAGMA key = \"x'{key}'\""  # raw key, no KDF; value is hex-validated above


def connect(path: Path | str, key: str | None, **kw: Any) -> Any:
    """Open a DB-API connection, keyed when ``key`` is given."""
    if key is None:
        return sqlite3.connect(str(path), **kw)
    if _sqlcipher is None:
        raise RuntimeError("database is encrypted but SQLCipher (sqlcipher3-wheels) is not installed")
    conn = _sqlcipher.connect(str(path), **kw)
    conn.execute(_key_pragma(key))
    return conn


def is_plaintext(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    with open(path, "rb") as f:
        return f.read(16) == PLAINTEXT_HEADER


def export(src: Path, src_key: str | None, dst: Path, dst_key: str | None) -> None:
    """Copy a whole database between encrypted/plaintext forms using SQLCipher's sqlcipher_export."""
    if _sqlcipher is None:
        raise RuntimeError("SQLCipher is required for encrypted export/import")
    dst.unlink(missing_ok=True)
    conn = _sqlcipher.connect(str(src))
    try:
        if src_key:
            conn.execute(_key_pragma(src_key))
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        attach_key = f"\"x'{dst_key}'\"" if dst_key else "''"
        if dst_key:
            _key_pragma(dst_key)  # validate
        conn.execute(f"ATTACH DATABASE ? AS target KEY {attach_key}", (str(dst),))
        conn.execute("SELECT sqlcipher_export('target')")
        ver = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.execute(f"PRAGMA target.user_version = {int(ver)}")
        conn.execute("DETACH DATABASE target")
    finally:
        conn.close()


def encrypt_in_place(path: Path, key: str) -> bool:
    """Convert a plaintext database to SQLCipher. Returns True if a conversion happened."""
    if not is_plaintext(path):
        return False
    plain = sqlite3.connect(str(path))
    plain.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    plain.execute("PRAGMA journal_mode=DELETE")
    plain.close()
    tmp = path.with_suffix(".encrypting")
    export(path, None, tmp, key)
    check = connect(tmp, key)
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("encrypted copy failed integrity check; plaintext database left untouched")
    finally:
        check.close()
    for suffix in ("-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)
    os.replace(tmp, path)
    return True
