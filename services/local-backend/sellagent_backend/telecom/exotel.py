"""Exotel AgentStream telephony provider (production calling route).

Exotel places the real cellular call and streams both sides of the live audio to SELL AGENT over a bidirectional
WebSocket (the AgentStream "Voicebot/Stream" protocol): raw linear16 PCM, base64-encoded inside JSON ``media``
events, 8 kHz by default (16/24 kHz selectable), chunks a multiple of 320 bytes, max 60-minute session. That is
the same shape as the AudioSocket path already in this repo, so the existing local loop (faster-whisper ->
conversation engine with approved FITRON facts + guardrails + female persona -> Piper TTS, barge-in, opt-out)
runs over it unchanged.

Responsibilities split:
  * Exotel dials the number and owns the PSTN/caller-ID leg (an Exotel ExoPhone, NOT the user's Jio number -
    see docs/EXOTEL_EVALUATION.md; do not claim the Jio number as caller ID without written Exotel confirmation).
  * SELL AGENT keeps ALL AI local; it never sends audio to a cloud AI. Exotel only carries telephony audio.

Security: the WebSocket endpoint Exotel connects to is token-authenticated and must be exposed only through an
authenticated tunnel/relay (docs/PROVIDER_SETUP.md), never as an open audio server. Credentials come from the
environment (EXOTEL_API_KEY / EXOTEL_API_TOKEN / EXOTEL_SID), never from the repo or the settings DB.

Nothing here bypasses the release gate: a real streamed call must be verified before autonomous calling is
allowed, and promotional campaigns stay disabled until Indian DLT/TRAI requirements are met
(docs/COMPLIANCE_INDIA.md).
"""

from __future__ import annotations

import base64
import os
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

import numpy as np
from sqlalchemy.orm import Session, sessionmaker

from sellagent_backend.services import settings_service
from sellagent_backend.telecom.android import audio_gate_status
from sellagent_backend.telecom.base import RouteCapabilities

DEFAULT_SAMPLE_RATE = 8_000


def exotel_credentials() -> dict[str, str]:
    """Read Exotel API credentials from the environment only. Empty strings when unset."""
    return {
        "api_key": os.getenv("EXOTEL_API_KEY", ""),
        "api_token": os.getenv("EXOTEL_API_TOKEN", ""),
        "sid": os.getenv("EXOTEL_SID", ""),
        "subdomain": os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com"),
    }


class ExotelStreamTransport:
    """One Exotel AgentStream WebSocket session as a ``MediaTransport``. The async WebSocket handler decodes
    inbound ``media`` events into PCM frames here, and drains outbound frames to send back as ``media`` events.
    recv()/send() are called from the conversation loop's thread; both ends are bounded and thread-safe."""

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, frame_ms: int = 20, inbound_cap: int = 200) -> None:
        self.sample_rate = sample_rate
        self.frame_bytes = int(sample_rate * frame_ms / 1_000) * 2  # PCM16 mono
        self._inbound: deque[bytes] = deque(maxlen=inbound_cap)  # filled by the WS task
        self._outbound: deque[bytes] = deque()  # filled by send(), drained by the WS task
        self._lock = threading.Lock()
        self._open = True
        self.clear_requested = False  # set when the loop cancels queued speech (barge-in) -> send Exotel "clear"

    # ---- called by the async WebSocket handler -------------------------------------------------
    def feed_inbound(self, pcm: bytes) -> None:
        with self._lock:
            # Re-chunk arbitrary inbound sizes into exact frames.
            self._carry = getattr(self, "_carry", b"") + pcm
            while len(self._carry) >= self.frame_bytes:
                self._inbound.append(self._carry[: self.frame_bytes])
                self._carry = self._carry[self.frame_bytes :]

    def drain_outbound(self, max_frames: int = 50) -> list[bytes]:
        out = []
        with self._lock:
            for _ in range(max_frames):
                if not self._outbound:
                    break
                out.append(self._outbound.popleft())
        return out

    def take_clear(self) -> bool:
        with self._lock:
            c = self.clear_requested
            self.clear_requested = False
            return c

    # ---- MediaTransport (called from the loop thread) ------------------------------------------
    def recv(self) -> bytes | None:
        with self._lock:
            try:
                return self._inbound.popleft()
            except IndexError:
                return None

    def send(self, frame: bytes) -> None:
        if not self._open or len(frame) != self.frame_bytes:
            return
        with self._lock:
            self._outbound.append(frame)

    def request_clear(self) -> None:
        with self._lock:
            self.clear_requested = True

    def is_connected(self) -> bool:
        return self._open

    def close(self) -> None:
        self._open = False


class ExotelProvider:
    """Telephony provider adapter for the ``exotel`` route. Dials via the Exotel API and hands the autonomous loop
    a verified audio path once the AgentStream WebSocket for that call is connected - and only when the release
    gate is satisfied. Caller ID is the configured ExoPhone, never the user's Jio number."""

    route = "exotel"

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory
        self._sessions: dict[str, ExotelStreamTransport] = {}
        self._lock = threading.Lock()
        self.http_post: Callable[..., Any] | None = None  # tests inject; real dial uses httpx

    # ---- stream lifecycle (driven by the WebSocket route) --------------------------------------
    def bind(self, call_id: str, transport: ExotelStreamTransport) -> None:
        with self._lock:
            self._sessions[call_id] = transport

    def unbind(self, call_id: str) -> None:
        with self._lock:
            t = self._sessions.pop(call_id, None)
        if t is not None:
            t.close()

    def transport_for(self, call_id: str) -> ExotelStreamTransport | None:
        with self._lock:
            return self._sessions.get(call_id)

    def resolve_call(self, call_id: str) -> str | None:
        from sellagent_backend.db.models import Call

        cid = (call_id or "").strip()
        with self._sf() as s:
            c = s.get(Call, cid)
            return c.id if c is not None else None

    # ---- configuration -------------------------------------------------------------------------
    def _config(self, s: Session) -> dict[str, Any]:
        creds = exotel_credentials()
        return {
            "enabled": bool(settings_service.get(s, "provider.enabled")) and settings_service.get(s, "provider.kind") == "exotel",
            "exophone": settings_service.get(s, "provider.caller_id"),
            "sample_rate": int(settings_service.get(s, "provider.sample_rate")),
            "stream_url": settings_service.get(s, "provider.stream_public_url"),
            "configured": bool(creds["api_key"] and creds["api_token"] and creds["sid"]),
            "creds": creds,
        }

    def capabilities(self) -> RouteCapabilities:
        with self._sf() as s:
            cfg = self._config(s)
            gate = audio_gate_status(s, None)
        notes: list[str] = []
        if not cfg["enabled"]:
            notes.append("Exotel provider not enabled (Settings: provider.*)")
        if cfg["enabled"] and not cfg["configured"]:
            notes.append("Exotel API credentials missing (set EXOTEL_API_KEY/TOKEN/SID in the environment)")
        if cfg["enabled"] and not cfg["stream_url"]:
            notes.append("No AgentStream public URL configured (needs an authenticated tunnel; see PROVIDER_SETUP.md)")
        if not gate["allowed"]:
            notes.append("two-way audio NOT verified on a real streamed call yet; autonomous mode blocked")
        notes.append("caller ID is the Exotel ExoPhone, not the Jio number")
        ready = cfg["enabled"] and cfg["configured"] and bool(cfg["stream_url"])
        return RouteCapabilities(
            route=self.route, can_dial=ready, reports_call_state=ready,
            remote_audio_capture=gate["remote_audio_capture_verified"], audio_injection=gate["audio_injection_verified"],
            autonomous_supported=gate["allowed"] and ready, notes=notes,
        )

    async def dial(self, *, call_job_id: str, e164: str, display_name: str | None, mode: str, authorization_token: str, language: str, device_id: str | None) -> tuple[bool, str]:
        with self._sf() as s:
            cfg = self._config(s)
            from sqlalchemy import select

            from sellagent_backend.db.models import Call

            call = s.scalar(select(Call).where(Call.call_job_id == call_job_id).order_by(Call.created_at.desc()))
            call_id = call.id if call else call_job_id
        if not cfg["enabled"]:
            return False, "Exotel provider is not enabled (Settings: provider.*)"
        if not cfg["configured"]:
            return False, "Exotel API credentials are not set (EXOTEL_API_KEY/TOKEN/SID)"
        if not cfg["exophone"]:
            return False, "No Exotel caller ID (ExoPhone) configured (Settings: provider.caller_id)"
        if not cfg["stream_url"]:
            return False, "No AgentStream public URL configured (Settings: provider.stream_public_url)"
        # Originate the call through Exotel's Connect API with a Stream applet pointing at our StreamUrl, tagging
        # the stream with our call_id (CustomField) so the WebSocket binds to the right conversation.
        creds = cfg["creds"]
        stream_url = f"{cfg['stream_url']}?call_id={call_id}&sample-rate={cfg['sample_rate']}"
        payload = {
            "From": cfg["exophone"], "To": e164, "CallerId": cfg["exophone"],
            "Url": f"http://my.exotel.com/{creds['sid']}/exoml/start_voice/STREAM",  # Stream applet; configured in Exotel dashboard
            "CustomField": call_id, "StreamUrl": stream_url,
        }
        post = self.http_post
        if post is None:
            try:
                import httpx  # noqa: PLC0415

                url = f"https://{creds['api_key']}:{creds['api_token']}@{creds['subdomain']}/v1/Accounts/{creds['sid']}/Calls/connect"
                async with httpx.AsyncClient(timeout=20) as client:
                    r = await client.post(url, data=payload)
                ok = r.status_code // 100 == 2
                return ok, (f"Exotel accepted the call (HTTP {r.status_code})" if ok else f"Exotel refused the call: HTTP {r.status_code} {r.text[:200]}")
            except Exception as exc:  # noqa: BLE001
                return False, f"Exotel dial failed: {exc}"
        ok, msg = await post(payload=payload, creds=creds)  # test hook
        return ok, msg

    async def cancel(self, *, call_job_id: str, device_id: str | None, reason: str) -> bool:
        with self._sf() as s:
            call_id = None
            from sqlalchemy import select

            from sellagent_backend.db.models import Call

            call = s.scalar(select(Call).where(Call.call_job_id == call_job_id).order_by(Call.created_at.desc()))
            call_id = call.id if call else None
        if call_id:
            self.unbind(call_id)
        return True

    def call_audio_path(self, call_id: str):  # type: ignore[no-untyped-def]
        """Verified path, or None. None when the gate is closed, the provider is off, or the Exotel stream for
        this call is not connected. A connected stream alone is never enough - the gate still rules."""
        from sellagent_backend.telecom.media_gateway import SipRtpCallAudioPath

        with self._sf() as s:
            cfg = self._config(s)
            if not cfg["enabled"]:
                return None
            if not audio_gate_status(s, None)["allowed"]:
                return None
        t = self.transport_for(call_id)
        if t is None or not t.is_connected():
            return None
        return SipRtpCallAudioPath(transport=t)


def decode_media_event(msg: dict[str, Any]) -> bytes | None:
    """Pull PCM bytes out of an Exotel AgentStream ``media`` event. Field names per the AgentStream Voicebot
    protocol (confirm against your account's docs): {"event":"media","media":{"payload":"<base64 pcm>"}}."""
    if msg.get("event") != "media":
        return None
    payload = (msg.get("media") or {}).get("payload")
    if not isinstance(payload, str) or not payload:
        return None
    try:
        return base64.b64decode(payload)
    except Exception:  # noqa: BLE001
        return None


def encode_media_event(pcm: bytes, stream_sid: str = "") -> dict[str, Any]:
    """Wrap outbound PCM as an Exotel ``media`` event to play to the caller."""
    ev: dict[str, Any] = {"event": "media", "media": {"payload": base64.b64encode(pcm).decode("ascii")}}
    if stream_sid:
        ev["stream_sid"] = stream_sid
    return ev


def pcm_from_float(audio: np.ndarray) -> bytes:  # convenience for tests
    return (np.clip(np.asarray(audio, dtype=np.float32), -1, 1) * 32767).astype("<i2").tobytes()
