"""Asterisk AudioSocket transport for the modular media gateway.

This is the concrete seam for the "USB cellular modem -> Asterisk -> local AI" architecture
(``docs/CALLING_ARCHITECTURE.md``). Asterisk bridges a live call to SELL AGENT with
``AudioSocket(<call-uuid>,127.0.0.1:<port>)``; Asterisk is the TCP client, SELL AGENT runs the server here. The
call's audio is 8 kHz mono slin, 320 bytes per 20 ms frame - exactly what Asterisk's ``app_audiosocket`` and
``chan_modemmanager`` carry. Each accepted connection becomes a :class:`MediaTransport` bound to the matching
call, so the existing local pipeline (faster-whisper STT, the conversation engine, the female Piper TTS, barge-in,
cancellation, CRM) runs over it unchanged.

Wire format (one frame): byte 0 = type, bytes 1-2 = big-endian payload length, then payload.
  0x00 HANGUP  (no payload)   0x01 UUID (16 bytes)   0x10 AUDIO (320-byte slin)   0xff ERROR (1 byte)

Security: the server binds to loopback only (never the LAN), accepts one connection per call, and drops anything
that is not a valid frame. It never opens the autonomous loop by itself - the release gate and
``MediaGatewayAdapter`` still decide that. No paid service, no cloud: plain local TCP to a local Asterisk.
"""

from __future__ import annotations

import logging
import socket
import struct
import threading
from collections import deque
from collections.abc import Callable

log = logging.getLogger("sellagent.audiosocket")

TYPE_HANGUP = 0x00
TYPE_UUID = 0x01
TYPE_AUDIO = 0x10
TYPE_ERROR = 0xFF
SAMPLE_RATE = 8_000
FRAME_BYTES = SAMPLE_RATE * 20 // 1_000 * 2  # 320: 20 ms slin mono


class AudioSocketTransport:
    """One AudioSocket connection as a :class:`MediaTransport`. The server's reader thread fills an inbound queue;
    the autonomy thread calls :meth:`send` to write AI audio. Both ends are frame-aligned 320-byte slin."""

    sample_rate = SAMPLE_RATE

    def __init__(self, conn: socket.socket, inbound_cap: int = 200) -> None:
        self._conn = conn
        self._inbound: deque[bytes] = deque(maxlen=inbound_cap)  # drop-oldest if the AI consumer stalls
        self._send_lock = threading.Lock()
        self._open = True

    def feed(self, frame: bytes) -> None:
        """Called by the reader thread with one decoded AUDIO payload."""
        self._inbound.append(frame)

    def recv(self) -> bytes | None:
        try:
            return self._inbound.popleft()
        except IndexError:
            return None

    def send(self, frame: bytes) -> None:
        if not self._open or len(frame) != FRAME_BYTES:
            return
        pkt = struct.pack(">BH", TYPE_AUDIO, len(frame)) + frame
        with self._send_lock:
            try:
                self._conn.sendall(pkt)
            except OSError:
                self._open = False

    def is_connected(self) -> bool:
        return self._open

    def close(self) -> None:
        if not self._open:
            return
        self._open = False
        with self._send_lock:
            try:
                self._conn.sendall(struct.pack(">BH", TYPE_HANGUP, 0))
            except OSError:
                pass
            try:
                self._conn.close()
            except OSError:
                pass


def read_frame(conn: socket.socket) -> tuple[int, bytes] | None:
    """Read exactly one AudioSocket frame. Returns (type, payload) or None on EOF / malformed header."""
    header = _recv_exactly(conn, 3)
    if header is None:
        return None
    ftype, length = struct.unpack(">BH", header)
    payload = _recv_exactly(conn, length) if length else b""
    if payload is None:
        return None
    return ftype, payload


def _recv_exactly(conn: socket.socket, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        try:
            chunk = conn.recv(n - len(buf))
        except OSError:
            return None
        if not chunk:
            return None
        buf += chunk
    return bytes(buf)


class AudioSocketServer:
    """Loopback TCP server that turns each Asterisk AudioSocket call into a bound :class:`MediaTransport`.

    ``resolve(uuid_hex) -> call_id | None`` maps the AudioSocket UUID (set in the Asterisk dialplan) to a SELL
    AGENT call id; unknown ids are refused. ``bind``/``unbind`` are the adapter's registration hooks. Nothing
    starts the AI here - the autonomy manager does, and only when the release gate is open."""

    def __init__(self, host: str, port: int, *, resolve: Callable[[str], str | None], bind: Callable[[str, AudioSocketTransport], None], unbind: Callable[[str], None]) -> None:
        self.host = host
        self.port = port
        self._resolve = resolve
        self._bind = bind
        self._unbind = unbind
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self.port))
        s.listen(4)
        self._sock = s
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, name="audiosocket-accept", daemon=True)
        self._thread.start()
        log.info("AudioSocket server listening on %s:%d (loopback)", self.host, self.port)

    def stop(self) -> None:
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    @property
    def bound_port(self) -> int:
        return self._sock.getsockname()[1] if self._sock else self.port

    def _accept_loop(self) -> None:
        while self._running and self._sock is not None:
            try:
                conn, _addr = self._sock.accept()
            except OSError:
                break
            threading.Thread(target=self._serve, args=(conn,), name="audiosocket-conn", daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        call_id: str | None = None
        transport: AudioSocketTransport | None = None
        try:
            first = read_frame(conn)
            if first is None or first[0] != TYPE_UUID or len(first[1]) != 16:
                log.warning("AudioSocket connection without a valid UUID frame; refusing")
                conn.close()
                return
            uuid_hex = first[1].hex()
            call_id = self._resolve(uuid_hex)
            if call_id is None:
                log.warning("AudioSocket UUID %s does not match a known call; refusing", uuid_hex)
                conn.close()
                return
            transport = AudioSocketTransport(conn)
            self._bind(call_id, transport)
            log.info("AudioSocket call %s bound", call_id)
            while True:
                frame = read_frame(conn)
                if frame is None or frame[0] == TYPE_HANGUP:
                    break
                ftype, payload = frame
                if ftype == TYPE_AUDIO and len(payload) == FRAME_BYTES:
                    transport.feed(payload)
                # other frame types (ERROR, DTMF, silence) are ignored for the audio bridge
        except Exception:  # noqa: BLE001 - a bad connection must never take the server down
            log.exception("AudioSocket connection error")
        finally:
            if transport is not None:
                transport.close()
            if call_id is not None:
                self._unbind(call_id)
                log.info("AudioSocket call %s unbound", call_id)
            try:
                conn.close()
            except OSError:
                pass
