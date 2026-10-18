"""Modular audio gateway (calling Approach C): a documented, business-logic-free seam that carries one live
call's DIGITAL audio between SELL AGENT and an external, independently qualified telephony gateway.

The gateway is NOT this phone. It is a separate, authorised device or trunk that already has a real two-way
audio path - for example a dedicated Qualcomm handset running a GSM<->SIP bridge, or a licensed SIP/PSTN trunk
(see ``docs/CALLING_ARCHITECTURE.md``). The Samsung Galaxy S25 on Jio provides none of this
(``docs/S25_COMPATIBILITY.md``); this module is the interface such a route plugs into, so the conversation loop
never has to know how the audio is obtained.

Design rules enforced here:

* **Separation.** The gateway only moves PCM frames and reports health/errors. It holds no FITRON knowledge, no
  consent logic and no persona. The conversation engine consumes :class:`CallAudioPath` and is unchanged.
* **Least privilege / restricted exposure.** The local media endpoint binds to loopback only and requires a
  shared secret; it is never an open audio server on the Wi-Fi. No Android capture, no root, no acoustic relay.
* **Bounded, backpressured.** Inbound frames live in a bounded jitter buffer that drops the OLDEST frame when a
  slow consumer falls behind, so a hostile or stalled peer cannot grow memory without bound.
* **Fail-closed.** A path is handed out only when the release gate is satisfied by real-device evidence AND a
  gateway is actually bound for that call. Silence, stall or disconnect make :meth:`is_open` return ``False`` and
  the autonomous loop falls back to the operator.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
from sqlalchemy.orm import Session, sessionmaker

from sellagent_backend.services import settings_service
from sellagent_backend.telecom.android import audio_gate_status
from sellagent_backend.telecom.base import RouteCapabilities

SR = 16_000
FRAME_MS = 20
SAMPLES_PER_FRAME = SR * FRAME_MS // 1_000  # 320
BYTES_PER_FRAME = SAMPLES_PER_FRAME * 2  # PCM16 mono


class GatewayError(RuntimeError):
    def __init__(self, msg: str, code: str) -> None:
        super().__init__(msg)
        self.code = code


class MediaTransport(Protocol):
    """A connected, frame-oriented, bidirectional PCM16 mono link to the external gateway for one call.

    Concrete transports (an Asterisk AudioSocket connection at 8 kHz, a loopback TCP socket to a local SIP media
    relay, a USB-forwarded stream from a dedicated gateway phone, a test loopback) all look the same to the path
    above. ``sample_rate`` is the PCM rate of the frames on this transport; ``recv`` is non-blocking and returns
    one 20 ms frame (``sample_rate*0.02*2`` bytes) or ``None`` when nothing has arrived yet."""

    sample_rate: int

    def recv(self) -> bytes | None: ...

    def send(self, frame: bytes) -> None: ...

    def is_connected(self) -> bool: ...

    def close(self) -> None: ...


class LoopbackTransport:
    """In-memory transport pair for tests and local soak runs: whatever one side sends, the other receives.
    No sockets, no real telephony - it exercises the path/queue/backpressure logic deterministically."""

    sample_rate = SR

    def __init__(self, inbound: deque[bytes], outbound: deque[bytes], peer_open: Callable[[], bool]) -> None:
        self._in = inbound
        self._out = outbound
        self._peer_open = peer_open  # reads the peer's OWN open flag; never calls back into is_connected()
        self._open = True

    def recv(self) -> bytes | None:
        try:
            return self._in.popleft()
        except IndexError:
            return None

    def send(self, frame: bytes) -> None:
        if self._open:
            self._out.append(frame)

    def is_connected(self) -> bool:
        return self._open and self._peer_open()

    def close(self) -> None:
        self._open = False

    @staticmethod
    def pair(maxlen: int = 400) -> tuple[LoopbackTransport, LoopbackTransport]:
        a_to_b: deque[bytes] = deque(maxlen=maxlen)
        b_to_a: deque[bytes] = deque(maxlen=maxlen)
        holder: dict[str, LoopbackTransport] = {}
        app = LoopbackTransport(b_to_a, a_to_b, lambda: holder["gw"]._open)
        gw = LoopbackTransport(a_to_b, b_to_a, lambda: holder["app"]._open)
        holder["app"], holder["gw"] = app, gw
        return app, gw


@dataclass
class SipRtpCallAudioPath:
    """``CallAudioPath`` over a :class:`MediaTransport`. PCM16/16 kHz on the wire, float32 mono in [-1, 1] to the
    conversation loop. Inbound frames sit in a bounded jitter buffer (drop-oldest). ``write`` paces itself to real
    time one frame at a time so the loop's barge-in watch stays aligned with what the caller actually hears."""

    transport: MediaTransport
    name: str = "media-gateway"
    sample_rate: int = SR
    jitter_frames: int = 150  # 3 s cap; older inbound audio is dropped under backpressure
    health_timeout_s: float = 4.0
    pace: Callable[[float], None] = time.sleep
    now: Callable[[], float] = time.monotonic

    _frame_bytes: int = 0
    _buf: deque[np.ndarray] = field(default_factory=lambda: deque(maxlen=150))
    _tx_tail: bytes = b""
    _closed: bool = False
    _last_rx: float = field(default_factory=time.monotonic)
    _started: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        self.sample_rate = getattr(self.transport, "sample_rate", self.sample_rate)
        self._frame_bytes = int(self.sample_rate * FRAME_MS / 1_000) * 2  # PCM16 mono 20 ms frame
        self._buf = deque(maxlen=self.jitter_frames)
        self._last_rx = self._started = self.now()

    def _drain(self) -> None:
        while True:
            frame = self.transport.recv()
            if frame is None:
                break
            if len(frame) != self._frame_bytes:  # ignore partial/garbage frames, never crash the call
                continue
            self._buf.append(np.frombuffer(frame, dtype="<i2").astype(np.float32) / 32768.0)
            self._last_rx = self.now()

    def read(self) -> np.ndarray:
        if self._closed:
            return np.zeros(0, dtype=np.float32)
        self._drain()
        if not self._buf:
            return np.zeros(0, dtype=np.float32)
        out = np.concatenate(list(self._buf))
        self._buf.clear()
        return out

    def write(self, chunk: np.ndarray) -> None:
        if self._closed or not self.transport.is_connected():
            return
        pcm = np.clip(np.asarray(chunk, dtype=np.float32), -1.0, 1.0)
        raw = self._tx_tail + (pcm * 32767.0).astype("<i2").tobytes()
        off = 0
        while off + self._frame_bytes <= len(raw):
            self.transport.send(raw[off : off + self._frame_bytes])
            off += self._frame_bytes
            self.pace(FRAME_MS / 1_000.0)  # roughly real time, so caller audio stays in step
            self._drain()  # keep reading caller audio while we speak (barge-in)
        self._tx_tail = raw[off:]

    def is_open(self) -> bool:
        if self._closed or not self.transport.is_connected():
            return False
        # Treat a prolonged inbound silence as a dead path only after the call has had a chance to start.
        if self.now() - self._started < self.health_timeout_s:
            return True
        return (self.now() - self._last_rx) < self.health_timeout_s

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                self.transport.close()
            except Exception:  # noqa: BLE001, S110 - closing never raises into the call
                pass


class MediaGatewayAdapter:
    """Telecom adapter for the external audio gateway route. Dialling and call control are delegated to the bound
    gateway's control channel (registered by whatever integration owns it); this class owns the audio seam and the
    fail-closed checks. An external gateway binds a live call's transport with :meth:`bind` and clears it with
    :meth:`unbind`."""

    route = "media_gateway"

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory
        self._sessions: dict[str, MediaTransport] = {}
        self._lock = threading.Lock()
        # Dial/cancel/health hooks are installed by a concrete gateway integration when one is configured.
        self.control: object | None = None
        self.pace: Callable[[float], None] = time.sleep  # tests set a no-op to run frame pacing instantly

    # ---- lifecycle a concrete gateway drives -------------------------------------------------
    def bind(self, call_id: str, transport: MediaTransport) -> None:
        with self._lock:
            self._sessions[call_id] = transport

    def unbind(self, call_id: str) -> None:
        with self._lock:
            self._sessions.pop(call_id, None)

    def is_bound(self, call_id: str) -> bool:
        with self._lock:
            t = self._sessions.get(call_id)
        return t is not None and t.is_connected()

    def resolve_uuid(self, uuid_hex: str) -> str | None:
        """Map an Asterisk AudioSocket UUID (the dialplan passes the SELL AGENT call id) to a live call id, or
        None. The call id is a 32-char hex string == the 16-byte AudioSocket UUID."""
        call_id = uuid_hex.replace("-", "").lower()
        if len(call_id) != 32:
            return None
        from sellagent_backend.db.models import Call

        with self._sf() as s:
            c = s.get(Call, call_id)
            return c.id if c is not None else None

    # ---- TelecomAdapter -----------------------------------------------------------------------
    def capabilities(self) -> RouteCapabilities:
        with self._sf() as s:
            gate = audio_gate_status(s, None)
            enabled = bool(settings_service.get(s, "gateway.enabled"))
        notes: list[str] = []
        if not enabled:
            notes.append("external audio gateway not configured (Settings: gateway.*)")
        if not gate["allowed"]:
            notes.append("two-way DIGITAL call audio NOT verified on a real route; autonomous mode blocked")
        return RouteCapabilities(
            route=self.route,
            can_dial=enabled and getattr(self.control, "can_dial", False),
            reports_call_state=enabled and getattr(self.control, "reports_call_state", False),
            remote_audio_capture=gate["remote_audio_capture_verified"],
            audio_injection=gate["audio_injection_verified"],
            autonomous_supported=gate["allowed"] and enabled,
            notes=notes,
        )

    async def dial(self, *, call_job_id: str, e164: str, display_name: str | None, mode: str, authorization_token: str, language: str, device_id: str | None) -> tuple[bool, str]:
        with self._sf() as s:
            if not settings_service.get(s, "gateway.enabled"):
                return False, "external audio gateway not configured (Settings: gateway.*)"
        ctl = self.control
        if ctl is not None and getattr(ctl, "can_dial", False):
            return await ctl.dial(call_job_id=call_job_id, e164=e164, display_name=display_name, mode=mode, authorization_token=authorization_token, language=language, device_id=device_id)  # type: ignore[attr-defined]
        # No direct control channel: the external gateway (SIP trunk / dedicated gateway phone) places the cellular
        # leg itself and reports call state back over its own link. The backend accepts the dispatch and waits.
        return True, "accepted: the external audio gateway places the call and reports state; SELL AGENT bridges audio"

    async def cancel(self, *, call_job_id: str, device_id: str | None, reason: str) -> bool:
        ctl = self.control
        if ctl is None or not getattr(ctl, "can_dial", False):
            return False
        return await ctl.cancel(call_job_id=call_job_id, device_id=device_id, reason=reason)  # type: ignore[attr-defined]

    def call_audio_path(self, call_id: str) -> SipRtpCallAudioPath | None:
        """A verified digital path, or None. None whenever the release gate is closed or no gateway is bound to
        this call - the autonomous loop then refuses to start (``no_verified_audio_path``) and the operator keeps
        the call. A bound transport alone is never enough; the gate still requires real-device evidence."""
        with self._sf() as s:
            if not settings_service.get(s, "gateway.enabled"):
                return None
            if not audio_gate_status(s, None)["allowed"]:
                return None
        with self._lock:
            transport = self._sessions.get(call_id)
        if transport is None or not transport.is_connected():
            return None
        return SipRtpCallAudioPath(transport=transport, pace=self.pace)
