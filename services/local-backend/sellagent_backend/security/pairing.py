"""In-memory pairing window. A pairing code is valid for a short time, allows a bounded number of
attempts, and must be approved by the Windows user before a device token is issued (mutual approval)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sellagent_backend.security.tokens import (
    expiry,
    generate_pairing_code,
    is_expired,
    normalize_pairing_code,
)


@dataclass
class PendingPairing:
    device_public_id: str
    device_name: str
    device_model: str
    android_version: str
    app_version: str
    capabilities: dict
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    approved: bool | None = None  # None = awaiting Windows user
    device_id: str | None = None
    token_once: str | None = None  # populated on approval; cleared after delivery


@dataclass
class PairingWindow:
    code: str
    expires_at: datetime
    attempts_left: int
    pending: PendingPairing | None = None

    @property
    def active(self) -> bool:
        return not is_expired(self.expires_at)


class PairingManager:
    def __init__(self, ttl_seconds: int = 300, max_attempts: int = 5) -> None:
        self._ttl = ttl_seconds
        self._max_attempts = max_attempts
        self._window: PairingWindow | None = None
        self._lock = threading.Lock()

    def open_window(self) -> PairingWindow:
        with self._lock:
            self._window = PairingWindow(
                code=generate_pairing_code(), expires_at=expiry(self._ttl), attempts_left=self._max_attempts
            )
            return self._window

    def close_window(self) -> None:
        with self._lock:
            self._window = None

    def current(self) -> PairingWindow | None:
        with self._lock:
            if self._window and not self._window.active:
                self._window = None
            return self._window

    def submit(self, code: str, pending: PendingPairing) -> str:
        """Returns 'pending' | 'invalid' | 'expired'. Consumes one attempt per wrong code."""
        with self._lock:
            w = self._window
            if w is None or not w.active:
                return "expired"
            if w.attempts_left <= 0:
                self._window = None
                return "expired"
            if normalize_pairing_code(code) != normalize_pairing_code(w.code):
                w.attempts_left -= 1
                if w.attempts_left <= 0:
                    self._window = None
                return "invalid"
            if w.pending is not None and w.pending.device_public_id != pending.device_public_id:
                return "invalid"  # another device already claimed this window
            w.pending = pending
            return "pending"

    def pending(self) -> PendingPairing | None:
        w = self.current()
        return w.pending if w else None

    def decide(self, approve: bool, device_id: str | None = None, token_once: str | None = None) -> PendingPairing | None:
        with self._lock:
            w = self._window
            if w is None or w.pending is None:
                return None
            w.pending.approved = approve
            w.pending.device_id = device_id
            w.pending.token_once = token_once
            if not approve:
                self._window = None
            return w.pending

    def take_token(self, device_public_id: str) -> PendingPairing | None:
        """Hand the one-time token to the device and close the window."""
        with self._lock:
            w = self._window
            if w is None or w.pending is None or w.pending.device_public_id != device_public_id:
                return None
            if w.pending.approved is not True:
                return w.pending
            p = w.pending
            self._window = None
            return p
