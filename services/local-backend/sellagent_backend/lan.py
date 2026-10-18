"""Optional LAN listener for Android pairing/WebSocket. Separate uvicorn server, TLS with the self-signed
certificate, only device-facing routes mounted. Started only when the operator enables it."""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

import uvicorn
from fastapi import FastAPI

log = logging.getLogger("sellagent.lan")


def local_ips() -> list[str]:
    ips: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except socket.gaierror:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ips)


class LanServer:
    def __init__(self, device_app: FastAPI, host: str, port: int, certfile: str, keyfile: str, fingerprint: str) -> None:
        self.device_app, self.host, self.port, self.certfile, self.keyfile, self.fingerprint = device_app, host, port, certfile, keyfile, fingerprint
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[Any] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return
        cfg = uvicorn.Config(self.device_app, host=self.host, port=self.port, log_level="warning", ssl_certfile=self.certfile, ssl_keyfile=self.keyfile, ws_ping_interval=20, ws_ping_timeout=20)
        self._server = uvicorn.Server(cfg)
        self._server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
        self._task = asyncio.create_task(self._server.serve())
        await asyncio.sleep(0.2)
        log.warning("LAN pairing listener started on https://%s:%s (TLS fingerprint %s)", self.host, self.port, self.fingerprint)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, 5)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self._task, self._server = None, None
        log.warning("LAN pairing listener stopped")

    def status(self) -> dict:
        return {"enabled": self.running, "host": self.host, "port": self.port, "scheme": "https/wss", "addresses": local_ips(), "tls_fingerprint_sha256": self.fingerprint, "exposes": ["/api/v1/health/ping", "/api/v1/devices/pair", "/api/v1/devices/pair/result", "/api/v1/devices/me", "/api/v1/ws/device"]}
