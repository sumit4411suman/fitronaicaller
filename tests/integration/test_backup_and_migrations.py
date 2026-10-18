from pathlib import Path

import pytest
from sellagent_backend.db import make_engine, migrate
from sellagent_backend.services import backup
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.conftest import make_contact

pytestmark = pytest.mark.automated


def test_migrations_upgrade_downgrade_upgrade(tmp_path):
    eng = make_engine(tmp_path / "m.db")
    migrate.upgrade(eng)
    assert migrate.is_up_to_date(eng)
    with eng.connect() as c:
        tables = {r[0] for r in c.execute(text("select name from sqlite_master where type='table'"))}
    assert {"contacts", "call_jobs", "knowledge_chunks_fts", "schema_version", "audio_tests"} <= tables
    migrate.downgrade(eng, "base")
    with eng.connect() as c:
        tables = {r[0] for r in c.execute(text("select name from sqlite_master where type='table'"))}
    assert "contacts" not in tables and "knowledge_chunks_fts" not in tables
    migrate.upgrade(eng)
    assert migrate.is_up_to_date(eng)
    eng.dispose()


def test_foreign_keys_enforced(db):
    from sellagent_backend.db.models import ContactPermission

    db.add(ContactPermission(contact_id="does-not-exist", status="granted", source="x"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_transaction_rollback_on_failed_import(client, settings):
    """A failing row mid-commit must not leave partial writes."""
    from sellagent_backend.db import make_session_factory
    from sellagent_backend.services import import_export

    sf = make_session_factory(client.app.state.engine)
    parsed = import_export.parse_file("g.csv", b"business,phone\nA,9876543210\nB,9123456780\n")
    with sf() as s:
        # simulate a crash after first create by passing an invalid campaign id (FK violation at flush)
        with pytest.raises(IntegrityError):
            import_export.commit(s, parsed, parsed.suggested_mapping, campaign_id="missing-campaign")
            s.commit()
        s.rollback()
    assert client.get("/api/v1/contacts").json()["total"] == 0


def test_backup_encrypted_roundtrip_and_restore(client, settings):
    make_contact(client)
    assert client.post("/api/v1/backup", json={}).status_code == 400  # encryption on -> passphrase required
    info = client.post("/api/v1/backup", json={"passphrase": "correct horse battery"}).json()
    assert info["encrypted"] and Path(info["path"]).exists() and Path(info["path"]).suffix == ".sabk"
    raw = Path(info["path"]).read_bytes()
    assert b"Power Gym" not in raw and b"+919876543210" not in raw  # confidentiality
    assert client.post("/api/v1/backup/verify", json={"path": info["path"], "passphrase": "wrong-passphrase", "confirm": "RESTORE"}).status_code == 400
    v = client.post("/api/v1/backup/verify", json={"path": info["path"], "passphrase": "correct horse battery", "confirm": "RESTORE"}).json()
    assert v["ok"] and "contacts" in v["tables"]
    # path traversal / outside dir rejected
    assert client.post("/api/v1/backup/verify", json={"path": str(settings.db_path), "passphrase": "x", "confirm": "RESTORE"}).status_code == 400
    # mutate, then restore
    make_contact(client, business_name="Later", phone="9123456780")
    assert client.get("/api/v1/contacts").json()["total"] == 2
    r = client.post("/api/v1/backup/restore", json={"path": info["path"], "passphrase": "correct horse battery", "confirm": "RESTORE"})
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/contacts").json()["total"] == 1
    assert Path(r.json()["pre_restore_copy"]).exists()
    assert len(client.get("/api/v1/backup").json()) == 1


def test_backup_retention_and_plaintext_policy(settings, engine):
    from sellagent_backend.db import crypto

    key = crypto.get_or_create_key(settings.data_dir)
    if key is not None:
        assert engine.info["encrypted"] and not crypto.is_plaintext(settings.db_path)
        with pytest.raises(backup.BackupError):  # encrypted DB never produces a plaintext backup
            backup.create_backup(settings.db_path, settings.backups_dir, passphrase=None, app_version="t", key=key)
    for _ in range(4):
        backup.create_backup(settings.db_path, settings.backups_dir, passphrase="long enough pass", app_version="t", keep=2, key=key)
    files = backup.list_backups(settings.backups_dir)
    assert len(files) == 2
    assert backup.verify_backup(Path(files[0]["path"]), "long enough pass")["ok"]


def test_plaintext_database_is_encrypted_in_place(tmp_path):
    import sqlite3

    from sellagent_backend.db import crypto

    if not crypto.available():
        pytest.skip("SQLCipher not installed")
    p = tmp_path / "legacy.db"
    c = sqlite3.connect(p)
    c.execute("create table t(x)")
    c.execute("insert into t values ('Power Gym +919876543210')")
    c.commit()
    c.close()
    key = "ab" * 32
    eng = make_engine(p, key=key)
    with eng.connect() as conn:
        assert conn.execute(text("select x from t")).scalar() == "Power Gym +919876543210"
    eng.dispose()
    raw = p.read_bytes()
    assert not raw.startswith(crypto.PLAINTEXT_HEADER) and b"Power Gym" not in raw
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(p).execute("select * from t").fetchall()
