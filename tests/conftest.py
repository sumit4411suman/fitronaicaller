"""Shared fixtures. Every test gets a fresh temporary data directory and database (migrated with Alembic)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sellagent_backend.app import create_app
from sellagent_backend.config import Settings, reset_settings
from sellagent_backend.db import make_engine, make_session_factory, migrate
from sqlalchemy.orm import Session

LOCAL_TOKEN = "test-local-token-0123456789abcdef"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    os.environ["SELLAGENT_DATA_DIR"] = str(tmp_path / "data")
    s = reset_settings(data_dir=tmp_path / "data", lan_enabled=False, llm_provider="none")
    s.ensure_dirs()
    return s


@pytest.fixture
def engine(settings: Settings):
    eng = make_engine(settings.db_path)
    migrate.upgrade(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:
    sf = make_session_factory(engine)
    s = sf()
    try:
        yield s
        s.commit()
    finally:
        s.close()


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, local_token=LOCAL_TOKEN)
    with TestClient(app, headers={"Authorization": f"Bearer {LOCAL_TOKEN}"}) as c:
        yield c


@pytest.fixture
def anon(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, local_token=LOCAL_TOKEN)
    with TestClient(app) as c:
        yield c


def make_contact(client: TestClient, **over) -> dict:
    body = {"business_name": "Power Gym", "contact_person": "Rahul", "phone": "+91 98765 43210", "city": "Bokaro", "consent_status": "granted"}
    body.update(over)
    r = client.post("/api/v1/contacts", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def grant_consent(client: TestClient, contact_id: str) -> None:
    r = client.post(f"/api/v1/contacts/{contact_id}/permissions", json={"status": "granted", "source": "existing customer inquiry form", "evidence": "form #123"})
    assert r.status_code == 201, r.text


def open_hours(client: TestClient) -> None:
    """Disable quiet hours and spacing so eligibility tests are deterministic regardless of wall-clock time."""
    r = client.patch("/api/v1/settings", json={"values": {"calling.quiet_hours_start": "00:00", "calling.quiet_hours_end": "00:00", "calling.min_seconds_between_calls": 0, "calling.max_calls_per_hour": 100, "calling.max_calls_per_day": 100}})
    assert r.status_code == 200, r.text
