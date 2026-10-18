"""Local users, roles and JWT sessions.

* The desktop bootstraps with the DPAPI-protected local token, which acts as the built-in ``owner`` (admin).
* Additional operators sign in with username + PIN and receive a JWT (HS256, 12 h) carrying their role.
  The signing secret is random, stored DPAPI-protected in ``<data dir>/jwt_secret``.
* Changing a user's role, disabling them or resetting their PIN bumps ``token_version`` which revokes
  every JWT issued before.
"""

from __future__ import annotations

import base64
import contextvars
import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt

from sellagent_backend.security.secret_store import read_secret_file, write_secret_file
from sellagent_backend.security.tokens import generate_token

ROLES = ("admin", "manager", "operator", "viewer")
JWT_TTL = timedelta(hours=12)
JWT_ISSUER = "sellagent-local"

_ALL_AREAS = (
    "health", "auth", "contacts", "suppression", "campaigns", "calls", "followups", "knowledge", "ai", "speech",
    "reports", "audit", "settings", "backup", "devices", "audio_tests", "users", "system",
)
_READ_ALL = {f"{a}:read" for a in _ALL_AREAS}

PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},
    "manager": (_READ_ALL - {"users:read"}) | {f"{a}:write" for a in ("contacts", "suppression", "campaigns", "calls", "followups", "knowledge", "ai", "speech", "reports", "audio_tests", "system")},
    "operator": {f"{a}:read" for a in ("health", "auth", "contacts", "suppression", "campaigns", "calls", "followups", "knowledge", "ai", "speech", "reports", "settings", "devices", "audio_tests", "system")}
    | {f"{a}:write" for a in ("contacts", "suppression", "calls", "followups", "ai", "speech")},
    "viewer": {f"{a}:read" for a in ("health", "auth", "contacts", "campaigns", "calls", "followups", "knowledge", "reports", "settings", "devices", "system")},
}

current_actor: contextvars.ContextVar[str | None] = contextvars.ContextVar("sellagent_actor", default=None)


@dataclass(frozen=True)
class Principal:
    actor: str
    role: str
    user_id: str | None = None
    via: str = "local_token"  # local_token | jwt

    def can(self, permission: str) -> bool:
        perms = PERMISSIONS.get(self.role, set())
        return "*" in perms or permission in perms


# ----------------------------------------------------------------------------- PIN hashing (scrypt)
_N, _R, _P = 2**14, 8, 1


def validate_pin(pin: str) -> None:
    if not re.fullmatch(r"\d{6,12}", pin or ""):
        raise ValueError("PIN must be 6 to 12 digits")
    if len(set(pin)) == 1 or pin in "0123456789012" or pin in "9876543210987":
        raise ValueError("PIN is too easy to guess (repeated or sequential digits)")


def hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pin.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        calc = hashlib.scrypt(pin.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


# ----------------------------------------------------------------------------- JWT
def jwt_secret(data_dir: Path) -> str:
    p = data_dir / "jwt_secret"
    s = read_secret_file(p)
    if not s:
        s = generate_token(48)
        write_secret_file(p, s)
    return s


def issue_jwt(secret: str, *, user_id: str, username: str, role: str, token_version: int, now: datetime | None = None) -> tuple[str, datetime]:
    now = now or datetime.now(UTC)
    exp = now + JWT_TTL
    payload = {"sub": user_id, "usr": username, "role": role, "ver": token_version, "iat": int(now.timestamp()), "exp": int(exp.timestamp()), "iss": JWT_ISSUER}
    return jwt.encode(payload, secret, algorithm="HS256"), exp


def decode_jwt(secret: str, token: str) -> dict | None:
    try:
        return jwt.decode(token, secret, algorithms=["HS256"], issuer=JWT_ISSUER, options={"require": ["exp", "iat", "sub", "role", "ver"]})
    except jwt.PyJWTError:
        return None


def looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2 and token.startswith("eyJ")
