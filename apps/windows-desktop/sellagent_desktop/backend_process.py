"""Start/stop the local backend as a child process and obtain the local API token.

Rules (see docs/DESKTOP_APP.md):
* If ``SELLAGENT_BACKEND_URL`` is set, the desktop connects to that running backend and never spawns one.
* Otherwise the backend is started on 127.0.0.1:8765 (``SELLAGENT_BACKEND_PORT`` overrides) using the
  bundled ``sellagent-backend.exe`` next to the app when frozen, or ``sys.executable -m sellagent_backend.main``.
* The child is terminated when the desktop exits. The token is read from ``<data_dir>/local_api_token``
  (DPAPI-protected on Windows) via the backend's own ``secret_store`` reader.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

from sellagent_desktop import paths

log = logging.getLogger("sellagent.desktop.backend")
DEFAULT_PORT = 8765


class BackendStartError(RuntimeError):
    pass


def read_local_token(data_dir: Path) -> str | None:
    token_file = data_dir / "local_api_token"
    try:
        from sellagent_backend.security.secret_store import read_secret_file

        return read_secret_file(token_file)
    except ImportError:
        # Minimal reader for the PLAIN1 format (non-Windows); DPAPI blobs need the backend package.
        import base64

        if not token_file.exists():
            return None
        blob = token_file.read_bytes()
        if blob.startswith(b"PLAIN1:"):
            return base64.b64decode(blob[7:]).decode("utf-8")
        raise BackendStartError("token file is DPAPI protected but the backend package is not importable")


class BackendProcess:
    def __init__(self, data_dir: Path | None = None, port: int | None = None):
        self.data_dir = data_dir or paths.data_dir()
        self.port = port or int(os.environ.get("SELLAGENT_BACKEND_PORT", DEFAULT_PORT))
        self.external_url = os.environ.get("SELLAGENT_BACKEND_URL")
        self.proc: subprocess.Popen | None = None
        self.base_url = self.external_url.rstrip("/") if self.external_url else f"http://127.0.0.1:{self.port}"
        self.log_path = self.data_dir / "logs" / "backend-child.log"
        self.token: str | None = None

    # ------------------------------------------------------------------ helpers
    def _command(self) -> list[str]:
        if paths.is_frozen():
            exe = paths.app_root() / ("sellagent-backend.exe" if sys.platform == "win32" else "sellagent-backend")
            if not exe.exists():
                raise BackendStartError(f"bundled backend not found at {exe}")
            return [str(exe), "--port", str(self.port)]
        return [sys.executable, "-m", "sellagent_backend.main", "--port", str(self.port)]

    def ping(self, timeout: float = 1.5) -> dict | None:
        try:
            r = httpx.get(f"{self.base_url}/api/v1/health/ping", timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except httpx.HTTPError:
            return None
        return None

    # ------------------------------------------------------------------ lifecycle
    def start(self, wait_seconds: float = 40.0) -> str:
        """Ensure a backend is reachable; returns its base URL. Spawns the child only when needed."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "logs").mkdir(parents=True, exist_ok=True)
        if self.external_url:
            if self.ping(3.0) is None:
                raise BackendStartError(f"SELLAGENT_BACKEND_URL={self.external_url} is not answering /api/v1/health/ping")
        elif self.ping() is None:
            env = dict(os.environ)
            env.setdefault("SELLAGENT_DATA_DIR", str(self.data_dir))
            env.setdefault("PYTHONUNBUFFERED", "1")
            creation = 0
            if sys.platform == "win32":
                creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            log_fh = open(self.log_path, "ab")  # noqa: SIM115 - kept open for the child's lifetime
            self.proc = subprocess.Popen(self._command(), env=env, stdout=log_fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=creation, cwd=str(paths.app_root()))
            log.info("started backend pid %s on %s", self.proc.pid, self.base_url)
            deadline = time.time() + wait_seconds
            while time.time() < deadline:
                if self.proc.poll() is not None:
                    raise BackendStartError(f"backend exited early with code {self.proc.returncode}; see {self.log_path}")
                if self.ping():
                    break
                time.sleep(0.25)
            else:
                self.stop()
                raise BackendStartError(f"backend did not become ready within {wait_seconds:.0f}s; see {self.log_path}")
        # token file is written during backend startup
        deadline = time.time() + 10
        while time.time() < deadline:
            self.token = read_local_token(self.data_dir)
            if self.token:
                break
            time.sleep(0.2)
        if not self.token:
            raise BackendStartError(f"local API token not found in {self.data_dir / 'local_api_token'}")
        return self.base_url

    def stop(self) -> None:
        p = self.proc
        if p is None:
            return
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=5)
        self.proc = None

    @property
    def owns_process(self) -> bool:
        return self.proc is not None
