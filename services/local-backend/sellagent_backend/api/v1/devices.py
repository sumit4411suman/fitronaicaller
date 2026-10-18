"""Pairing + device management. Operator-facing endpoints need the local token; device-facing endpoints are
also mounted on the LAN listener and are rate-limited."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sellagent_protocol import PROTOCOL_VERSION
from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_device_auth, require_local_auth
from sellagent_backend.api.schemas import DeviceOut, Ok, PairingDecision, PairingRequestIn
from sellagent_backend.api.v1.errors import bad_request, not_found
from sellagent_backend.db.models import PairedDevice
from sellagent_backend.security.pairing import PendingPairing
from sellagent_backend.security.tokens import generate_token, hash_token
from sellagent_backend.services import audit

router = APIRouter(prefix="/devices", tags=["devices"], dependencies=[Depends(require_local_auth)])
device_public_router = APIRouter(prefix="/devices", tags=["devices-public"])

_attempts: dict[str, list[float]] = {}


def _rate_limited(ip: str, limit: int = 10, window: int = 60) -> bool:
    now = time.time()
    hits = [t for t in _attempts.get(ip, []) if now - t < window]
    hits.append(now)
    _attempts[ip] = hits
    return len(hits) > limit


# ------------------------------------------------------------------ operator side
@router.post("/pairing/open")
def open_pairing(request: Request, db: Session = Depends(get_db)) -> dict:
    st = request.app.state
    w = st.pairing.open_window()
    audit.record(db, "pairing.window_open", severity="warning", data={"expires_at": w.expires_at.isoformat()})
    return {"pairing_code": w.code, "expires_at": w.expires_at, "attempts_left": w.attempts_left, "lan": st.lan.status() if st.lan else {"enabled": False}, "tls_fingerprint_sha256": st.tls_fingerprint, "protocol_version": PROTOCOL_VERSION, "instructions": "On the phone enter the LAN address, port, this code and verify the certificate fingerprint matches. Then approve the request here."}


@router.post("/pairing/close", response_model=Ok)
def close_pairing(request: Request, db: Session = Depends(get_db)) -> Ok:
    request.app.state.pairing.close_window()
    audit.record(db, "pairing.window_close")
    return Ok()


@router.get("/pairing/status")
def pairing_status(request: Request) -> dict:
    w = request.app.state.pairing.current()
    if w is None:
        return {"open": False}
    p = w.pending
    return {"open": True, "expires_at": w.expires_at, "attempts_left": w.attempts_left, "pending": None if p is None else {"device_public_id": p.device_public_id, "device_name": p.device_name, "device_model": p.device_model, "android_version": p.android_version, "app_version": p.app_version, "capabilities": p.capabilities, "requested_at": p.requested_at, "approved": p.approved}}


@router.post("/pairing/decide")
def decide(body: PairingDecision, request: Request, db: Session = Depends(get_db)) -> dict:
    st = request.app.state
    pending = st.pairing.pending()
    if pending is None:
        raise not_found("no pending pairing request")
    if not body.approve:
        st.pairing.decide(False)
        audit.record(db, "pairing.rejected", severity="warning", data={"device_public_id": pending.device_public_id})
        return {"approved": False}
    dev = db.scalar(select(PairedDevice).where(PairedDevice.device_public_id == pending.device_public_id))
    token = generate_token()
    expires = datetime.now(UTC) + timedelta(days=st.settings.device_token_ttl_days)
    if dev is None:
        dev = PairedDevice(device_public_id=pending.device_public_id, name=pending.device_name, model=pending.device_model, android_version=pending.android_version, app_version=pending.app_version)
        db.add(dev)
    dev.name, dev.model, dev.android_version, dev.app_version = pending.device_name, pending.device_model, pending.android_version, pending.app_version
    dev.token_hash, dev.token_expires_at, dev.status, dev.approved_at, dev.revoked_at = hash_token(token), expires, "approved", datetime.now(UTC), None
    dev.capabilities = {k: v for k, v in (pending.capabilities or {}).items() if k not in ("remote_audio_capture_verified", "audio_injection_verified")}  # never trust these from pairing
    db.flush()
    st.pairing.decide(True, device_id=dev.id, token_once=token)
    audit.record(db, "pairing.approved", severity="warning", entity_type="device", entity_id=dev.id, data={"device_public_id": dev.device_public_id, "model": dev.model})
    return {"approved": True, "device_id": dev.id, "token_expires_at": expires}


@router.get("", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db)) -> list[PairedDevice]:
    return list(db.scalars(select(PairedDevice).order_by(PairedDevice.created_at.desc())))


@router.get("/connected")
def connected(request: Request) -> dict:
    return {"connected": request.app.state.hub.connected_devices()}


@router.post("/{device_id}/revoke", response_model=DeviceOut)
async def revoke(device_id: str, request: Request, db: Session = Depends(get_db)) -> PairedDevice:
    dev = db.get(PairedDevice, device_id)
    if dev is None:
        raise not_found("device not found")
    dev.status, dev.token_hash, dev.revoked_at = "revoked", None, datetime.now(UTC)
    audit.record(db, "device.revoked", severity="warning", entity_type="device", entity_id=dev.id)
    db.commit()
    hub = request.app.state.hub
    ws = hub._devices.get(dev.id)
    if ws is not None:
        try:
            await ws.close(code=4001, reason="revoked")
        except Exception as exc:  # noqa: BLE001
            import logging

            logging.getLogger("sellagent.devices").warning("closing revoked device socket failed: %s", exc)
    return dev


@router.delete("/{device_id}", response_model=Ok)
def delete_device(device_id: str, db: Session = Depends(get_db)) -> Ok:
    dev = db.get(PairedDevice, device_id)
    if dev is None:
        raise not_found("device not found")
    if dev.status != "revoked":
        raise bad_request("revoke the device before deleting it")
    db.delete(dev)
    audit.record(db, "device.deleted", severity="warning", entity_type="device", entity_id=device_id)
    return Ok()


# ------------------------------------------------------------------ device side (also on LAN listener)
@device_public_router.post("/pair")
def pair(body: PairingRequestIn, request: Request, db: Session = Depends(get_db)) -> dict:
    ip = request.client.host if request.client else "?"
    if _rate_limited(ip):
        audit.record(db, "pairing.rate_limited", severity="warning", data={"ip": ip})
        raise bad_request("too many pairing attempts; wait a minute", code="rate_limited")
    pending = PendingPairing(device_public_id=body.device_public_id, device_name=body.device_name, device_model=body.device_model, android_version=body.android_version, app_version=body.app_version, capabilities=body.capabilities)
    status = request.app.state.pairing.submit(body.pairing_code, pending)
    audit.record(db, f"pairing.request.{status}", severity="info" if status == "pending" else "warning", data={"ip": ip, "device_public_id": body.device_public_id, "model": body.device_model})
    return {"status": status, "message": {"pending": "waiting for approval on the Windows PC", "invalid": "wrong pairing code", "expired": "pairing window closed; open it again on the PC"}[status], "protocol_version": PROTOCOL_VERSION}


@device_public_router.get("/pair/result")
def pair_result(device_public_id: str, request: Request) -> dict:
    """Device polls until approved; the token is returned exactly once."""
    p = request.app.state.pairing.take_token(device_public_id)
    if p is None:
        w = request.app.state.pairing.current()
        return {"status": "expired" if w is None else "unknown"}
    if p.approved is None:
        return {"status": "pending"}
    if p.approved is False:
        return {"status": "rejected"}
    tok, p.token_once = p.token_once, None
    return {"status": "approved", "device_id": p.device_id, "device_token": tok, "backend_name": "SELL AGENT", "protocol_version": PROTOCOL_VERSION, "ws_path": "/api/v1/ws/device"}


@device_public_router.get("/me", response_model=DeviceOut)
def me(dev: PairedDevice = Depends(require_device_auth)) -> PairedDevice:
    return dev
