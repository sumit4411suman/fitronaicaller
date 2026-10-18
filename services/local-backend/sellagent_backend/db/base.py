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


def make_engine(db_path: Path | str, *, echo: bool = False) -> Engine:
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    url = "sqlite:///:memory:" if str(db_path) == ":memory:" else f"sqlite:///{Path(db_path).as_posix()}"
    engine = create_engine(url, echo=echo, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _apply_pragmas)
    return engine


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
