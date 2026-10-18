"""HTTP client for the local backend plus a thread-pool helper so no network call ever runs on the UI thread.

* Bearer token from the backend's local token file, ``X-Request-ID`` per request, explicit timeouts.
* :class:`ApiError` carries the backend's ``error``/``code``/``request_id`` so screens can show them verbatim.
* :func:`call_async` runs a callable on ``QThreadPool`` and delivers the result/exception to the UI thread
  through queued signals. ``inflight()`` lets tests and the status bar know when the app is idle.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from collections.abc import Callable
from typing import Any

import httpx
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal

from sellagent_desktop import APP_VERSION

DEFAULT_TIMEOUT = 20.0
LONG_TIMEOUT = 600.0  # model pulls, loopback, backups


class ApiError(Exception):
    def __init__(self, status: int, error: str, code: str = "error", request_id: str | None = None, detail: Any = None):
        super().__init__(error)
        self.status, self.error, self.code, self.request_id, self.detail = status, error, code, request_id, detail

    role: str | None = None  # filled by ApiClient so 403s can name the current role

    def __str__(self) -> str:  # shown in toasts
        if self.status == 403:
            return f"Your role ({self.role or 'unknown'}) can't do this — {self.error}"
        return f"{self.error} [{self.code}, HTTP {self.status}]"

    @classmethod
    def from_response(cls, r: httpx.Response) -> ApiError:
        try:
            body = r.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        return cls(r.status_code, str(body.get("error") or body.get("detail") or r.reason_phrase or "request failed"), str(body.get("code") or "http_error"), body.get("request_id"), body.get("detail"))


class ApiClient:
    def __init__(self, base_url: str, token: str, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.owner_token = token  # the local (owner/admin) token; ``token`` may be a user's JWT after "Switch user"
        self.role: str | None = "admin"
        self.timeout = timeout
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, headers={"User-Agent": f"SellAgentDesktop/{APP_VERSION}"})
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ low level
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "X-Request-ID": uuid.uuid4().hex}

    def request(self, method: str, path: str, *, params: dict | None = None, json: Any = None, files: Any = None, data: Any = None, timeout: float | None = None, raw: bool = False) -> Any:
        if not path.startswith("/api/"):
            path = "/api/v1" + (path if path.startswith("/") else "/" + path)
        clean_params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        try:
            r = self._client.request(method, path, params=clean_params, json=json, files=files, data=data, headers=self._headers(), timeout=timeout or self.timeout)
        except httpx.TimeoutException as exc:
            raise ApiError(0, f"backend did not answer within {timeout or self.timeout:.0f}s", "timeout") from exc
        except httpx.HTTPError as exc:
            raise ApiError(0, f"cannot reach backend at {self.base_url}: {exc.__class__.__name__}", "connection_error") from exc
        if r.status_code >= 400:
            err = ApiError.from_response(r)
            err.role = self.role
            raise err
        if raw:
            return r
        if not r.content:
            return None
        ctype = r.headers.get("content-type", "")
        if "json" in ctype:
            return r.json()
        return r.content

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, json: Any = None, *, params: dict | None = None, timeout: float | None = None) -> Any:
        return self.request("POST", path, json=json, params=params, timeout=timeout)

    def patch(self, path: str, json: Any) -> Any:
        return self.request("PATCH", path, json=json)

    def delete(self, path: str, **params: Any) -> Any:
        return self.request("DELETE", path, params=params)

    def upload(self, path: str, filename: str, content: bytes, *, params: dict | None = None, field: str = "file") -> Any:
        return self.request("POST", path, files={field: (filename, content)}, params=params, timeout=LONG_TIMEOUT)

    def download(self, path: str, **params: Any) -> tuple[bytes, str]:
        r = self.request("GET", path, params=params, raw=True, timeout=LONG_TIMEOUT)
        name = "download"
        cd = r.headers.get("content-disposition", "")
        if "filename=" in cd:
            name = cd.split("filename=", 1)[1].strip().strip('"')
        return r.content, name

    def ws_url(self, path: str = "/api/v1/ws/desktop", **params: str) -> str:
        from urllib.parse import urlencode

        scheme = "wss" if self.base_url.startswith("https") else "ws"
        host = self.base_url.split("://", 1)[1]
        return f"{scheme}://{host}{path}?{urlencode({'token': self.token, **params})}"

    @property
    def is_owner(self) -> bool:
        return self.token == self.owner_token

    def stream_sse(self, path: str, json: Any, on_event: Callable[[str, Any], None], cancelled: Callable[[], bool] = lambda: False, timeout: float = LONG_TIMEOUT) -> None:
        """Blocking SSE reader (run it in a worker thread). Calls ``on_event(event_name, data)`` for every event;
        plain ``data:`` lines are delivered as event "message"."""
        import json as _json

        if not path.startswith("/api/"):
            path = "/api/v1" + path
        try:
            with self._client.stream("POST", path, json=json, headers={**self._headers(), "Accept": "text/event-stream"}, timeout=httpx.Timeout(timeout, connect=10)) as r:
                if r.status_code >= 400:
                    r.read()
                    err = ApiError.from_response(r)
                    err.role = self.role
                    raise err
                event, data_lines = "message", []
                for line in r.iter_lines():
                    if cancelled():
                        break
                    if line == "":
                        if data_lines:
                            raw = "\n".join(data_lines)
                            try:
                                payload: Any = _json.loads(raw)
                            except ValueError:
                                payload = raw
                            on_event(event, payload)
                        event, data_lines = "message", []
                    elif line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
        except httpx.HTTPError as exc:
            raise ApiError(0, f"stream failed: {exc.__class__.__name__}", "connection_error") from exc

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------- background workers
_inflight = 0
_inflight_lock = threading.Lock()
_keepalive: set[QObject] = set()


def inflight() -> int:
    with _inflight_lock:
        return _inflight


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Job(QRunnable):
    def __init__(self, fn: Callable[[], Any], signals: _Signals):
        super().__init__()
        self.fn, self.signals = fn, signals
        self.setAutoDelete(True)

    def run(self) -> None:
        global _inflight
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001 - delivered to the UI thread
            if not isinstance(exc, ApiError):
                exc.ui_traceback = traceback.format_exc()  # type: ignore[attr-defined]
            self.signals.failed.emit(exc)
        else:
            self.signals.done.emit(result)
        finally:
            with _inflight_lock:
                _inflight -= 1


def call_async(fn: Callable[[], Any], on_done: Callable[[Any], None] | None = None, on_error: Callable[[Exception], None] | None = None) -> None:
    """Run ``fn`` off the UI thread. Callbacks run on the thread that called ``call_async`` (the UI thread)."""
    global _inflight
    sig = _Signals()
    _keepalive.add(sig)

    def _finish() -> None:
        _keepalive.discard(sig)
        sig.deleteLater()

    def _ok(res: Any) -> None:
        try:
            if on_done:
                on_done(res)
        finally:
            _finish()

    def _err(exc: Exception) -> None:
        try:
            if on_error:
                on_error(exc)
        finally:
            _finish()

    sig.done.connect(_ok, Qt.ConnectionType.QueuedConnection)
    sig.failed.connect(_err, Qt.ConnectionType.QueuedConnection)
    with _inflight_lock:
        _inflight += 1
    QThreadPool.globalInstance().start(_Job(fn, sig))


def inflight_add(n: int) -> None:
    """Used by long-running QThreads (streams, transcription) so ``wait_for_idle`` waits for them too."""
    global _inflight
    with _inflight_lock:
        _inflight += n


def wait_for_idle(timeout_ms: int = 15000, settle_ms: int = 150) -> bool:
    """Process Qt events until no background request is running (used by tests and the setup wizard)."""
    from PySide6.QtCore import QCoreApplication, QElapsedTimer

    t = QElapsedTimer()
    t.start()
    while t.elapsed() < timeout_ms:
        QCoreApplication.processEvents()
        if inflight() == 0 and not _keepalive:
            settle = QElapsedTimer()
            settle.start()
            while settle.elapsed() < settle_ms:
                QCoreApplication.processEvents()
            if inflight() == 0 and not _keepalive:
                return True
    return inflight() == 0
