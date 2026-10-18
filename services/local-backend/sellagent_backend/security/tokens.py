"""Token and pairing-code primitives. Tokens are random, shown once and stored only as SHA-256 hashes."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from datetime import UTC, datetime, timedelta

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I ambiguity


def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(presented: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    return hmac.compare_digest(hash_token(presented), stored_hash)


def generate_pairing_code(length: int = 8) -> str:
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))
    return f"{raw[:4]}-{raw[4:]}" if length == 8 else raw


def normalize_pairing_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch in string.ascii_uppercase + string.digits)


def expiry(seconds: int) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)


def is_expired(when: datetime | None) -> bool:
    return when is not None and datetime.now(UTC) >= when
