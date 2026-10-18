"""Desktop WebSocket client (``/api/v1/ws/desktop``) on its own thread with an asyncio loop.

QtWebSockets is not part of PySide6-Essentials, so the ``websockets`` library is used. Every received
``Envelope`` is emitted as :attr:`WsClient.event` (a dict) on the UI thread. The connection auto-reconnects
with capped back-off. The client can also send ``safety.emergency_stop`` for lowest-latency stops.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any

from PySide6.QtCore import QThread, Signal

log = logging.getLogger("sellagent.desktop.ws")


class WsClient(QThread):
    event = Signal(dict)  # parsed Envelope
    connected_changed = Signal(bool)
    status_text = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = threading.Event()
        self._ws: Any = None
        self.is_connected = False
        self.last_event_at: float | None = None

    # ------------------------------------------------------------------ public API
    def stop(self) -> None:
        self._stop.set()
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._wake)
        self.wait(5000)

    def set_url(self, url: str) -> None:
        """Switch credentials (e.g. after 'Switch user'): the current socket is closed and the loop reconnects."""
        self.url = url
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._wake)

    def send_json(self, payload: dict) -> bool:
        loop, ws = self._loop, self._ws
        if loop is None or ws is None or not self.is_connected:
            return False
        fut = asyncio.run_coroutine_threadsafe(ws.send(json.dumps(payload)), loop)
        try:
            fut.result(timeout=3)
            return True
        except Exception:  # noqa: BLE001
            return False

    def send_emergency_stop(self, reason: str = "operator_emergency_stop") -> bool:
        try:
            from sellagent_protocol import EmergencyStop, Envelope, MessageType

            env = Envelope.of(MessageType.EMERGENCY_STOP, EmergencyStop(reason=reason[:200], issued_by="windows"))  # type: ignore[arg-type]
            return self.send_json(json.loads(env.model_dump_json()))
        except Exception:  # noqa: BLE001 - protocol package missing in an odd install; fall back to a hand-built envelope
            import uuid
            from datetime import UTC, datetime

            return self.send_json({"protocol_version": "1.0", "type": "safety.emergency_stop", "message_id": uuid.uuid4().hex, "sent_at": datetime.now(UTC).isoformat(), "payload": {"reason": reason[:200], "issued_by": "windows"}})

    # ------------------------------------------------------------------ thread body
    def _wake(self) -> None:
        ws = self._ws
        if ws is not None and self._loop is not None:
            self._loop.create_task(ws.close())

    def run(self) -> None:  # noqa: D401
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        finally:
            self._loop.close()
            self._loop = None

    async def _main(self) -> None:
        try:
            from websockets.asyncio.client import connect
        except ImportError:  # websockets < 13
            from websockets import connect  # type: ignore[no-redef]
        delay = 1.0
        while not self._stop.is_set():
            try:
                self.status_text.emit("connecting")
                self._last_url = self.url
                async with connect(self.url, max_size=256_000, ping_interval=20, ping_timeout=20, open_timeout=5) as ws:
                    self._ws = ws
                    self.is_connected = True
                    delay = 1.0
                    self.connected_changed.emit(True)
                    self.status_text.emit("connected")
                    async for raw in ws:
                        if self._stop.is_set():
                            break
                        try:
                            msg = json.loads(raw)
                        except ValueError:
                            continue
                        if isinstance(msg, dict):
                            self.last_event_at = time.time()
                            self.event.emit(msg)
            except Exception as exc:  # noqa: BLE001 - connection errors trigger reconnect
                self.status_text.emit(f"disconnected: {exc.__class__.__name__}")
            finally:
                if self.is_connected:
                    self.is_connected = False
                    self.connected_changed.emit(False)
                self._ws = None
            if self._stop.is_set():
                break
            await asyncio.sleep(0.2 if self.url != getattr(self, '_last_url', self.url) else delay)
            self._last_url = self.url
            delay = min(delay * 2, 15.0)
