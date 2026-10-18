"""Live transcription client: PC microphone -> /api/v1/ws/transcribe (PCM16 LE mono 16 kHz).

Runs in its own QThread with the synchronous ``websockets`` client. Audio is captured with ``sounddevice``
(PortAudio). If PortAudio is missing, :class:`MicUnavailable` explains how to fix it. Audio is never written to disk
by the app; the backend transcribes in memory and stores only text lines.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator

from PySide6.QtCore import QThread, Signal

from sellagent_desktop.api_client import inflight_add

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1600  # 100 ms


class MicUnavailable(RuntimeError):
    pass


def microphone_frames(stop: Callable[[], bool]) -> Iterator[bytes]:
    """Yield 100 ms PCM16 frames from the default input device until ``stop()`` is true."""
    try:
        import sounddevice as sd  # type: ignore
    except (ImportError, OSError) as exc:
        raise MicUnavailable(f"Microphone capture needs the 'sounddevice' package and the PortAudio library ({exc}). Install requirements-speech.txt; on Windows PortAudio ships inside the sounddevice wheel.") from exc
    if not hasattr(sd, "InputStream"):
        raise MicUnavailable("sounddevice is installed but PortAudio could not be loaded")
    try:
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME_SAMPLES)
    except Exception as exc:  # noqa: BLE001 - no device, permission denied, ...
        raise MicUnavailable(f"Cannot open the PC microphone: {exc}. Check Windows Settings › Privacy › Microphone.") from exc
    with stream:
        while not stop():
            data, _overflow = stream.read(FRAME_SAMPLES)
            yield data.tobytes()


class TranscriptionThread(QThread):
    message = Signal(dict)  # server messages: ready / vad / final / error
    status = Signal(str)
    finished_ok = Signal()

    def __init__(self, ws_url: str, frames: Callable[[Callable[[], bool]], Iterator[bytes]] = microphone_frames, parent=None):
        super().__init__(parent)
        self.ws_url = ws_url
        self.frames = frames
        self._stop = False
        self._pending: list[str] = []

    def stop(self) -> None:
        self._stop = True

    def set_speaker(self, speaker: str) -> None:
        self._pending.append(json.dumps({"type": "speaker", "speaker": speaker}))

    def run(self) -> None:
        inflight_add(1)
        try:
            self._run()
        finally:
            inflight_add(-1)
            self.finished_ok.emit()

    def _drain(self, ws) -> bool:  # type: ignore[no-untyped-def]
        """Read every queued server message; returns False when the server closed or sent an error."""
        while True:
            try:
                raw = ws.recv(timeout=0)
            except TimeoutError:
                return True
            except Exception:  # noqa: BLE001 - closed
                return False
            try:
                msg = json.loads(raw) if isinstance(raw, str) else {}
            except ValueError:
                continue
            self.message.emit(msg)
            if msg.get("type") == "error":
                return False

    def _run(self) -> None:
        from websockets.sync.client import connect

        self.status.emit("connecting")
        try:
            ws = connect(self.ws_url, open_timeout=10, max_size=256_000)
        except Exception as exc:  # noqa: BLE001
            self.message.emit({"type": "error", "code": "connect_failed", "error": str(exc)})
            return
        with ws:
            try:
                first = json.loads(ws.recv(timeout=15))
            except Exception as exc:  # noqa: BLE001
                self.message.emit({"type": "error", "code": "no_ready", "error": str(exc)})
                return
            self.message.emit(first)
            if first.get("type") != "ready":
                return
            self.status.emit("listening")
            try:
                for frame in self.frames(lambda: self._stop):
                    while self._pending:
                        ws.send(self._pending.pop(0))
                    ws.send(frame)
                    if not self._drain(ws):
                        return
                    if self._stop:
                        break
            except MicUnavailable as exc:
                self.message.emit({"type": "error", "code": "mic_unavailable", "error": str(exc)})
                return
            try:
                ws.send(json.dumps({"type": "stop"}))
                for _ in range(100):  # let the final segment arrive (<= ~10 s)
                    try:
                        raw = ws.recv(timeout=0.1)
                    except TimeoutError:
                        continue
                    msg = json.loads(raw) if isinstance(raw, str) else {}
                    self.message.emit(msg)
                    if msg.get("type") in ("final", "error"):
                        continue
            except Exception:  # noqa: BLE001 - server closed after stop: normal
                pass
        self.status.emit("stopped")
