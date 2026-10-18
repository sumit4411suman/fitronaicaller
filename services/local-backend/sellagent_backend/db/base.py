"""SQLite engine/session factory with WAL mode, foreign keys and busy timeout."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def _apply_pragmas(dbapi_conn: sqlite3.Connection, _record: object) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA temp_store=MEMORY")
    cur.close()


def make_engine(db_path: Path | str, *, key: str | None = None, echo: bool = False) -> Engine:
    """Create the SQLAlchemy engine. With ``key`` the file is opened through SQLCipher (encrypted at rest)."""
    from sellagent_backend.db import crypto

    if str(db_path) == ":memory:":
        engine = create_engine("sqlite:///:memory:", echo=echo, connect_args={"check_same_thread": False})
    else:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if key is not None:
            crypto.encrypt_in_place(path, key)
            engine = create_engine(
                f"sqlite:///{path.as_posix()}", echo=echo, module=crypto.dbapi(),
                creator=lambda: crypto.connect(path, key, check_same_thread=False),
            )
        else:
            engine = create_engine(f"sqlite:///{path.as_posix()}", echo=echo, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _apply_pragmas)
    engine.info = {"encrypted": key is not None}  # type: ignore[attr-defined]
    return engine


def engine_for(settings: object) -> Engine:
    """Engine for the configured data directory, encrypted whenever SQLCipher is available."""
    from sellagent_backend.db import crypto

    data_dir = settings.data_dir  # type: ignore[attr-defined]
    return make_engine(settings.db_path, key=crypto.get_or_create_key(data_dir))  # type: ignore[attr-defined]


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
