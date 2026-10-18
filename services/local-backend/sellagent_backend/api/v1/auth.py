"""Authentication: local token (owner), user login with PIN -> JWT, user and role management."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_area, require_local_auth
from sellagent_backend.api.v1.errors import bad_request, conflict, not_found
from sellagent_backend.db.models import User
from sellagent_backend.security import auth as A
from sellagent_backend.security.auth import Principal
from sellagent_backend.security.secret_store import write_secret_file
from sellagent_backend.security.tokens import generate_token, hash_token
from sellagent_backend.services import audit

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(require_area("auth"))])
public_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_area("users"))])

LOCKOUT_AFTER = 5
LOCKOUT_FOR = timedelta(minutes=5)
_login_hits: dict[str, list[float]] = {}


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    pin: str = Field(min_length=6, max_length=12)


class UserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=100)
    role: str
    pin: str


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = None
    role: str | None = None
    active: bool | None = None


class PinReset(BaseModel):
    pin: str


def _user_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role, "active": u.active, "last_login_at": u.last_login_at, "locked_until": u.locked_until, "created_at": u.created_at}


@router.get("/whoami")
def whoami(principal: Principal = Depends(require_local_auth)) -> dict:
    return {"actor": principal.actor, "role": principal.role, "user_id": principal.user_id, "via": principal.via, "permissions": sorted(A.PERMISSIONS[principal.role])}


@router.get("/roles")
def roles() -> dict:
    return {"roles": {r: sorted(p) for r, p in A.PERMISSIONS.items()}}


@router.post("/rotate-local-token")
def rotate(request: Request, db: Session = Depends(get_db)) -> dict:
    """Rotate the desktop<->backend owner token (admin only). Returned once and written to the protected token file."""
    token = generate_token()
    request.app.state.local_token_hash = hash_token(token)
    write_secret_file(request.app.state.settings.local_token_path, token)
    audit.record(db, "auth.rotate_local_token", severity="warning")
    return {"token": token}


@public_router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> dict:
    ip = request.client.host if request.client else "?"
    now_s = time.time()
    hits = [t for t in _login_hits.get(ip, []) if now_s - t < 60] + [now_s]
    _login_hits[ip] = hits
    if len(hits) > 20:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "rate_limited", "error": "too many login attempts; wait a minute"})
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    now = datetime.now(UTC)
    if user is None or not user.active:
        audit.record(db, "auth.login_failed", actor=body.username[:50], severity="warning", data={"reason": "unknown_or_disabled"})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "invalid_credentials", "error": "username or PIN is wrong"})
    if user.locked_until and user.locked_until > now:
        raise HTTPException(status.HTTP_423_LOCKED, detail={"code": "locked", "error": f"too many wrong PINs; try again after {user.locked_until.isoformat()}"})
    if not A.verify_pin(body.pin, user.pin_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= LOCKOUT_AFTER:
            user.locked_until, user.failed_attempts = now + LOCKOUT_FOR, 0
        audit.record(db, "auth.login_failed", actor=user.username, severity="warning", data={"reason": "bad_pin"})
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "invalid_credentials", "error": "username or PIN is wrong"})
    user.failed_attempts, user.locked_until, user.last_login_at = 0, None, now
    token, exp = A.issue_jwt(request.app.state.jwt_secret, user_id=user.id, username=user.username, role=user.role, token_version=user.token_version)
    audit.record(db, "auth.login", actor=user.username, data={"role": user.role})
    return {"token": token, "token_type": "bearer", "expires_at": exp, "user": _user_out(user), "permissions": sorted(A.PERMISSIONS[user.role])}


@public_router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db), principal: Principal = Depends(require_local_auth)) -> dict:
    """Revokes every session of the signed-in user (bumps token_version)."""
    if principal.user_id:
        u = db.get(User, principal.user_id)
        if u:
            u.token_version += 1
    audit.record(db, "auth.logout", actor=principal.actor)
    return {"ok": True}


@users_router.get("")
def list_users(db: Session = Depends(get_db)) -> list[dict]:
    return [_user_out(u) for u in db.scalars(select(User).order_by(User.username))]


@users_router.post("", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db)) -> dict:
    if body.role not in A.ROLES:
        raise bad_request(f"role must be one of {A.ROLES}")
    try:
        A.validate_pin(body.pin)
    except ValueError as exc:
        raise bad_request(str(exc), code="weak_pin") from exc
    if db.scalar(select(User).where(User.username == body.username)):
        raise conflict("username already exists")
    u = User(username=body.username, display_name=body.display_name, role=body.role, pin_hash=A.hash_pin(body.pin))
    db.add(u)
    db.flush()
    audit.record(db, "user.create", entity_type="user", entity_id=u.id, severity="warning", data={"username": u.username, "role": u.role})
    return _user_out(u)


@users_router.patch("/{user_id}")
def patch_user(user_id: str, body: UserPatch, db: Session = Depends(get_db)) -> dict:
    u = db.get(User, user_id)
    if u is None:
        raise not_found("user not found")
    if body.role is not None:
        if body.role not in A.ROLES:
            raise bad_request(f"role must be one of {A.ROLES}")
        if body.role != u.role:
            u.role, u.token_version = body.role, u.token_version + 1
    if body.active is not None and body.active != u.active:
        u.active, u.token_version = body.active, u.token_version + 1
    if body.display_name is not None:
        u.display_name = body.display_name
    audit.record(db, "user.update", entity_type="user", entity_id=u.id, severity="warning", data=body.model_dump(exclude_unset=True))
    return _user_out(u)


@users_router.post("/{user_id}/reset-pin")
def reset_pin(user_id: str, body: PinReset, db: Session = Depends(get_db)) -> dict:
    u = db.get(User, user_id)
    if u is None:
        raise not_found("user not found")
    try:
        A.validate_pin(body.pin)
    except ValueError as exc:
        raise bad_request(str(exc), code="weak_pin") from exc
    u.pin_hash, u.token_version, u.failed_attempts, u.locked_until = A.hash_pin(body.pin), u.token_version + 1, 0, None
    audit.record(db, "user.reset_pin", entity_type="user", entity_id=u.id, severity="warning")
    return _user_out(u)


@users_router.delete("/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db)) -> dict:
    u = db.get(User, user_id)
    if u is None:
        raise not_found("user not found")
    db.delete(u)
    audit.record(db, "user.delete", entity_type="user", entity_id=user_id, severity="warning")
    return {"ok": True}
