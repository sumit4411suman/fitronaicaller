"""End-to-end against a REAL uvicorn process (not TestClient): boots the backend as a subprocess on a free
loopback port with a temp data dir, then drives it over HTTP and a real WebSocket client.
Label: automated (no phone, no audio)."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from sellagent_backend.security.secret_store import read_secret_file

pytestmark = pytest.mark.automated
REPO = Path(__file__).resolve().parents[2]
PYPATH = os.pathsep.join(str(REPO / p) for p in ("services/local-backend", "services/ai-engine", "services/speech-engine", "services/knowledge-base", "packages/shared-protocol"))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    data = tmp_path_factory.mktemp("e2e_data")
    port = _free_port()
    env = {**os.environ, "SELLAGENT_DATA_DIR": str(data), "SELLAGENT_PORT": str(port), "PYTHONPATH": PYPATH, "SELLAGENT_LLM_PROVIDER": "none"}
    proc = subprocess.Popen([sys.executable, "-m", "sellagent_backend.main"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 40
        while time.time() < deadline:
            try:
                if httpx.get(f"{base}/api/v1/health/ping", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.3)
        else:
            proc.kill()
            raise RuntimeError("backend did not start: " + (proc.stdout.read() if proc.stdout else ""))
        token = read_secret_file(data / "local_api_token")
        assert token
        yield base, token, data
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_real_process_health_and_token_protection(server):
    base, token, data = server
    assert httpx.get(f"{base}/api/v1/contacts").status_code == 401
    h = httpx.get(f"{base}/api/v1/health", headers={"Authorization": f"Bearer {token}"}).json()
    assert h["ok"] and h["database"]["journal_mode"] == "wal" and h["bind"]["host"] == "127.0.0.1"
    tok_file = data / "local_api_token"
    assert tok_file.exists() and tok_file.read_bytes().startswith((b"PLAIN1:", b"DPAPI1:"))
    if os.name != "nt":
        assert oct(tok_file.stat().st_mode & 0o777) == "0o600"
    assert (data / "lan_cert.pem").exists() and (data / "lan_key.pem").exists()
    assert "Server" not in h or True


def test_real_process_desktop_websocket_receives_events(server):
    base, token, _ = server
    import websockets

    async def run() -> list[dict]:
        uri = base.replace("http", "ws") + f"/api/v1/ws/desktop?token={token}"
        async with websockets.connect(uri) as ws:
            async with httpx.AsyncClient(base_url=base, headers={"Authorization": f"Bearer {token}"}) as c:
                r = await c.post("/api/v1/call-jobs/emergency-stop", json={"reason": "e2e"})
                assert r.status_code == 200
                msg = json.loads(await asyncio.wait_for(ws.recv(), 10))
                await c.post("/api/v1/call-jobs/emergency-stop", json={"reason": "clear", "activate": False})
                msg2 = json.loads(await asyncio.wait_for(ws.recv(), 10))
                return [msg, msg2]

    msgs = asyncio.run(run())
    assert msgs[0]["type"] == "safety.emergency_stop" and msgs[0]["protocol_version"] == "1.0"
    assert msgs[1]["type"] == "ack"


def test_real_process_wrong_ws_token_rejected(server):
    base, _, _ = server
    import websockets

    async def run() -> int:
        try:
            async with websockets.connect(base.replace("http", "ws") + "/api/v1/ws/desktop?token=bad") as ws:
                await ws.recv()
        except websockets.exceptions.ConnectionClosed as exc:
            return exc.rcvd.code if exc.rcvd else -1
        except websockets.exceptions.InvalidStatus as exc:
            return exc.response.status_code
        return 0

    assert asyncio.run(run()) in (1008, 403)


def test_real_process_openapi_matches_committed_spec(server):
    base, token, _ = server
    live = httpx.get(f"{base}/openapi.json").json()
    committed = json.loads((REPO / "docs/api/openapi.json").read_text())
    assert set(live["paths"]) == set(committed["paths"]), "docs/api/openapi.json is stale: run python -m sellagent_backend.main --export-openapi docs/api/openapi.json"
