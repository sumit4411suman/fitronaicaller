"""FastAPI dependencies: DB session, local (desktop) auth, device auth, request ids."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.db.models import PairedDevice, User
from sellagent_backend.security.auth import Principal, current_actor, decode_jwt, looks_like_jwt
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


def resolve_principal(app_state: object, token: str | None) -> Principal | None:
    """Local token -> built-in owner (admin). JWT -> the signed-in local user, if still active and not revoked."""
    if not token:
        return None
    if tokens_match(token, app_state.local_token_hash):  # type: ignore[attr-defined]
        return Principal(actor="owner", role="admin")
    if not looks_like_jwt(token):
        return None
    claims = decode_jwt(app_state.jwt_secret, token)  # type: ignore[attr-defined]
    if claims is None:
        return None
    with app_state.session_factory() as s:  # type: ignore[attr-defined]
        user = s.get(User, claims["sub"])
        if user is None or not user.active or user.token_version != claims["ver"] or user.role != claims["role"]:
            return None
        return Principal(actor=user.username, role=user.role, user_id=user.id, via="jwt")


def require_local_auth(request: Request, authorization: str | None = Header(default=None), x_local_token: str | None = Header(default=None)) -> Principal:
    principal = resolve_principal(request.app.state, _bearer(authorization) or x_local_token)
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "unauthorized", "error": "local API token or session missing, invalid or expired"})
    request.state.principal = principal
    current_actor.set(principal.actor)
    return principal


def require_area(area: str):  # type: ignore[no-untyped-def]
    """Role check: GET/HEAD need '<area>:read', every other method needs '<area>:write'."""

    def _dep(request: Request, principal: Principal = Depends(require_local_auth)) -> Principal:
        perm = f"{area}:{'read' if request.method in ('GET', 'HEAD', 'OPTIONS') else 'write'}"
        if not principal.can(perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "forbidden", "error": f"role '{principal.role}' lacks permission {perm}"})
        return principal

    return _dep


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
