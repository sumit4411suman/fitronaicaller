import time

import pytest

from sellagent_backend.security.pairing import PairingManager, PendingPairing
from sellagent_backend.security.secret_store import protection_mode, read_secret_file, write_secret_file
from sellagent_backend.security.tokens import generate_pairing_code, generate_token, hash_token, normalize_pairing_code, tokens_match
from sellagent_backend.services.audit import redact

pytestmark = pytest.mark.automated


def test_tokens_hash_and_match():
    t = generate_token()
    assert len(t) >= 40 and tokens_match(t, hash_token(t)) and not tokens_match(t + "x", hash_token(t)) and not tokens_match(t, None)


def test_pairing_code_format():
    c = generate_pairing_code()
    assert len(c) == 9 and c[4] == "-" and not any(ch in c for ch in "0O1I")
    assert normalize_pairing_code("ab-cd ef") == "ABCDEF"


def _pending(pid="dev-public-1"):
    return PendingPairing(device_public_id=pid, device_name="S25", device_model="SM-S931B", android_version="15", app_version="0.1", capabilities={})


def test_pairing_window_attempts_and_expiry():
    pm = PairingManager(ttl_seconds=1, max_attempts=2)
    w = pm.open_window()
    assert pm.submit("WRONG-CODE", _pending()) == "invalid"
    assert pm.submit("WRONG-CODE", _pending()) == "invalid"
    assert pm.submit(w.code, _pending()) == "expired"  # attempts exhausted closes the window
    w = pm.open_window()
    time.sleep(1.1)
    assert pm.submit(w.code, _pending()) == "expired"


def test_pairing_mutual_approval_and_one_time_token():
    pm = PairingManager()
    w = pm.open_window()
    assert pm.submit(w.code.lower(), _pending()) == "pending"
    assert pm.take_token("dev-public-1").approved is None
    pm.decide(True, device_id="d1", token_once="tok")
    p = pm.take_token("dev-public-1")
    assert p.approved and p.token_once == "tok"
    assert pm.current() is None and pm.take_token("dev-public-1") is None


def test_second_device_cannot_hijack_window():
    pm = PairingManager()
    w = pm.open_window()
    assert pm.submit(w.code, _pending("a")) == "pending"
    assert pm.submit(w.code, _pending("b")) == "invalid"


def test_secret_file_roundtrip(tmp_path):
    p = tmp_path / "tok"
    write_secret_file(p, "s3cret")
    assert read_secret_file(p) == "s3cret" and protection_mode() in ("windows_dpapi", "file_permissions_only")
    if protection_mode() == "file_permissions_only":
        assert oct(p.stat().st_mode & 0o777) == "0o600"


def test_redact():
    out = redact({"device_token": "abc", "nested": {"api_key": "k", "x": 1}, "ok": "v"})
    assert out["device_token"] == "[REDACTED]" and out["nested"]["api_key"] == "[REDACTED]" and out["ok"] == "v"
