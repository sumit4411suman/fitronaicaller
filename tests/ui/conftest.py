"""UI test fixtures: a REAL backend subprocess on a free port with a temporary data directory, plus an
offscreen QApplication and a fully built MainWindow. Skips cleanly when PySide6 is not installed."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QT_LOGGING_RULES"] = "qt.text.font.db=false;qt.qpa.*=false"
os.environ["SELLAGENT_DESKTOP_SKIP_WIZARD"] = "1"

pytest.importorskip("PySide6", reason="PySide6 not installed; UI tests skipped")

ROOT = Path(__file__).resolve().parents[2]
PKG_PATHS = [ROOT / p for p in ("services/local-backend", "services/ai-engine", "services/speech-engine", "services/knowledge-base", "packages/shared-protocol", "apps/windows-desktop")]
for p in PKG_PATHS:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

pytestmark = pytest.mark.ui


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Backend:
    def __init__(self, url: str, token: str, data_dir: Path, proc: subprocess.Popen):
        self.url, self.token, self.data_dir, self.proc = url, token, data_dir, proc

    def client(self) -> httpx.Client:
        return httpx.Client(base_url=self.url, headers={"Authorization": f"Bearer {self.token}"}, timeout=20)


@pytest.fixture(scope="session")
def backend(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Backend]:
    data_dir = tmp_path_factory.mktemp("sellagent_ui_data")
    port = _free_port()
    env = dict(os.environ)
    env.update({
        "SELLAGENT_DATA_DIR": str(data_dir), "SELLAGENT_LLM_PROVIDER": "none", "SELLAGENT_LAN_ENABLED": "false",
        "PYTHONPATH": os.pathsep.join(str(p) for p in PKG_PATHS) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""),
        "PYTHONUNBUFFERED": "1",
    })
    env.pop("SELLAGENT_BACKEND_URL", None)
    log_fh = open(data_dir / "backend-stdout.log", "wb")  # noqa: SIM115
    proc = subprocess.Popen([sys.executable, "-m", "sellagent_backend.main", "--port", str(port)], env=env, cwd=str(ROOT), stdout=log_fh, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 60
    ok = False
    while time.time() < deadline:
        if proc.poll() is not None:
            log_fh.close()
            pytest.fail(f"backend exited early ({proc.returncode}): {(data_dir / 'backend-stdout.log').read_text()[-2000:]}")
        try:
            if httpx.get(f"{url}/api/v1/health/ping", timeout=1).status_code == 200:
                ok = True
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    if not ok:
        proc.terminate()
        pytest.fail("backend did not start within 60 s")
    from sellagent_backend.security.secret_store import read_secret_file

    token = None
    for _ in range(50):
        token = read_secret_file(data_dir / "local_api_token")
        if token:
            break
        time.sleep(0.2)
    assert token, "local token not written"
    # deterministic eligibility regardless of wall-clock: disable quiet hours and spacing
    with httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=20) as c:
        r = c.patch("/api/v1/settings", json={"values": {"calling.quiet_hours_start": "00:00", "calling.quiet_hours_end": "00:00", "calling.min_seconds_between_calls": 0, "calling.max_calls_per_hour": 100, "calling.max_calls_per_day": 100}})
        assert r.status_code == 200, r.text
    b = Backend(url, token, data_dir, proc)
    yield b
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log_fh.close()


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    from sellagent_desktop.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    yield app


@pytest.fixture(scope="session")
def window(qapp, backend: Backend):
    from sellagent_desktop.api_client import ApiClient, wait_for_idle
    from sellagent_desktop.context import AppContext
    from sellagent_desktop.main_window import MainWindow
    from sellagent_desktop.ws_client import WsClient

    api = ApiClient(backend.url, backend.token)
    ws = WsClient(api.ws_url())
    ws.start()
    ctx = AppContext(api=api, ws=ws, data_dir=backend.data_dir, backend_url=backend.url)
    win = MainWindow(ctx)
    win.show()
    wait_for_idle(20000)
    yield win
    win.close()
    ws.stop()
    api.close()


def wait_idle(timeout_ms: int = 20000) -> bool:
    from sellagent_desktop.api_client import wait_for_idle

    return wait_for_idle(timeout_ms)
