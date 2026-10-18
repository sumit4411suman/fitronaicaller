"""Protect small secrets at rest.

* Windows: DPAPI (``CryptProtectData`` via ctypes, current-user scope). This code path cannot be
  exercised on the Linux CI/dev container used to build this release; it is covered by
  ``tests/unit/test_secret_store.py`` only on Windows runners (see docs/TEST_REPORT.md).
* Other platforms: the secret is stored with 0600 permissions and a clear marker that it is not
  DPAPI-protected.

Nothing here disables any OS protection.
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

_PREFIX_DPAPI = b"DPAPI1:"
_PREFIX_PLAIN = b"PLAIN1:"


def _dpapi_available() -> bool:
    return sys.platform == "win32"


def _dpapi(data: bytes, protect: bool) -> bytes:  # pragma: no cover - Windows only
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), buf)
    blob_out = DATA_BLOB()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        raise OSError(f"DPAPI {'protect' if protect else 'unprotect'} failed: {ctypes.GetLastError()}")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def protect(data: bytes) -> bytes:
    if _dpapi_available():
        return _PREFIX_DPAPI + base64.b64encode(_dpapi(data, True))
    return _PREFIX_PLAIN + base64.b64encode(data)


def unprotect(blob: bytes) -> bytes:
    if blob.startswith(_PREFIX_DPAPI):
        if not _dpapi_available():
            raise OSError("secret was protected with Windows DPAPI and cannot be read on this platform")
        return _dpapi(base64.b64decode(blob[len(_PREFIX_DPAPI) :]), False)
    if blob.startswith(_PREFIX_PLAIN):
        return base64.b64decode(blob[len(_PREFIX_PLAIN) :])
    raise ValueError("unrecognised secret blob format")


def write_secret_file(path: Path, secret: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(protect(secret.encode("utf-8")))
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def read_secret_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return unprotect(path.read_bytes()).decode("utf-8")


def protection_mode() -> str:
    return "windows_dpapi" if _dpapi_available() else "file_permissions_only"
