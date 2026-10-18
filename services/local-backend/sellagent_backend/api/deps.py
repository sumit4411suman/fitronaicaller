"""FastAPI dependencies: DB session, local (desktop) auth, device auth, request ids."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.db.models import PairedDevice
from sellagent_backend.security.tokens import hash_token, is_expired, tokens_match


def get_db(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def request_id(x_request_id: str | None = Header(default=None)) -> str:
    return x_request_id or uuid.uuid4().hex


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def require_local_auth(request: Request, authorization: str | None = Header(default=None), x_local_token: str | None = Header(default=None)) -> str:
    token = _bearer(authorization) or x_local_token
    expected_hash: str = request.app.state.local_token_hash
    if not token or not tokens_match(token, expected_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "unauthorized", "error": "local API token missing or invalid"})
    return "operator"


def require_device_auth(request: Request, db: Session = Depends(get_db), authorization: str | None = Header(default=None), x_device_token: str | None = Header(default=None)) -> PairedDevice:
    token = _bearer(authorization) or x_device_token
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "unauthorized", "error": "device token missing"})
    dev = db.scalar(select(PairedDevice).where(PairedDevice.token_hash == hash_token(token)))
    if dev is None or dev.status != "approved" or is_expired(dev.token_expires_at):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "unauthorized", "error": "device token invalid, revoked or expired"})
    dev.last_seen_at = datetime.now(UTC)
    dev.last_ip = request.client.host if request.client else None
    return dev
