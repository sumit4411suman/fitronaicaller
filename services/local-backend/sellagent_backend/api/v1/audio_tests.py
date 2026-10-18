"""Audio feasibility test records. Real-device results arrive from the diagnostic APK over the WebSocket; the
operator confirms each on Windows; only confirmed real-device PASS rows can open the release gate."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_area
from sellagent_backend.api.schemas import AudioTestIn, AudioTestOut, Ok
from sellagent_backend.api.v1.errors import not_found
from sellagent_backend.db.models import AudioTest
from sellagent_backend.services import audit, settings_service
from sellagent_backend.telecom import audio_gate_status

router = APIRouter(prefix="/audio-tests", tags=["audio-tests"], dependencies=[Depends(require_area("audio_tests"))])

TEST_PLAN = [
    {"step": "pairing", "direction": "none", "title": "Secure pairing Windows <-> Android over the same Wi-Fi"},
    {"step": "call_state_reporting", "direction": "none", "title": "Call initiation + call-state events (dialing/ringing/active/disconnected)"},
    {"step": "outgoing_call", "direction": "none", "title": "Outgoing call to an authorized test number"},
    {"step": "remote_speech_capture", "direction": "inbound", "title": "Capture of the REMOTE party's speech by the app (not the local mic)"},
    {"step": "generated_speech_transmission", "direction": "outbound", "title": "Transmission of generated test speech INTO the call uplink"},
    {"step": "simultaneous_two_way", "direction": "both", "title": "Both directions at the same time"},
    {"step": "route_earpiece", "direction": "none", "title": "Audio route: earpiece"},
    {"step": "route_speaker", "direction": "none", "title": "Audio route: speakerphone"},
    {"step": "route_bluetooth", "direction": "none", "title": "Audio route: Bluetooth hands-free"},
    {"step": "route_wired", "direction": "none", "title": "Audio route: wired headset"},
    {"step": "latency_echo_quality", "direction": "both", "title": "Latency, echo, clipping, interruptions, intelligibility"},
    {"step": "screen_locked", "direction": "none", "title": "Operation with the screen locked / foreground service restrictions"},
    {"step": "wifi_interruption", "direction": "none", "title": "Wi-Fi drop, reconnection, cancellation, emergency stop"},
    {"step": "hindi_phrases", "direction": "both", "title": "Hindi test phrases"},
    {"step": "english_phrases", "direction": "both", "title": "English test phrases"},
    {"step": "jio_wifi_calling", "direction": "none", "title": "Behaviour when the phone is on Jio Wi-Fi Calling (VoWiFi) rather than another route"},
]


@router.get("/plan")
def plan() -> dict:
    return {"steps": TEST_PLAN, "rule": "A step is PASS only when observed on the real Galaxy S25 + Jio SIM and confirmed by the operator. Simulated/emulator results never count."}


@router.get("", response_model=list[AudioTestOut])
def list_tests(db: Session = Depends(get_db), test_id: str | None = None) -> list[AudioTest]:
    q = select(AudioTest).order_by(AudioTest.created_at.desc())
    if test_id:
        q = q.where(AudioTest.test_id == test_id)
    return list(db.scalars(q))


@router.post("", response_model=AudioTestOut, status_code=201)
def record(body: AudioTestIn, db: Session = Depends(get_db)) -> AudioTest:
    row = AudioTest(**body.model_dump())
    db.add(row)
    db.flush()
    audit.record(db, "audio_test.record", entity_type="audio_test", entity_id=row.id, severity="warning" if body.status == "pass" and body.kind == "real_device" else "info", data={"step": body.step, "status": body.status, "kind": body.kind})
    return row


@router.post("/{row_id}/confirm", response_model=AudioTestOut)
def confirm(row_id: str, db: Session = Depends(get_db), confirmed: bool = True) -> AudioTest:
    row = db.get(AudioTest, row_id)
    if row is None:
        raise not_found("audio test not found")
    row.operator_confirmed = confirmed
    audit.record(db, "audio_test.confirm", entity_type="audio_test", entity_id=row.id, severity="warning", data={"confirmed": confirmed, "step": row.step, "status": row.status, "kind": row.kind})
    gate = audio_gate_status(db)
    settings_service.set_release_gate(db, gate["allowed"], gate["evidence"])
    return row


@router.delete("/{row_id}", response_model=Ok)
def delete(row_id: str, db: Session = Depends(get_db)) -> Ok:
    row = db.get(AudioTest, row_id)
    if row is None:
        raise not_found("audio test not found")
    db.delete(row)
    db.flush()
    gate = audio_gate_status(db)
    settings_service.set_release_gate(db, gate["allowed"], gate["evidence"])
    return Ok()


@router.get("/report")
def report(db: Session = Depends(get_db), test_id: str | None = None) -> dict:
    rows = list_tests(db, test_id)
    by_step = {s["step"]: None for s in TEST_PLAN}
    for r in rows:
        if r.step in by_step and by_step[r.step] is None:
            by_step[r.step] = {"status": r.status, "kind": r.kind, "direction": r.direction, "confirmed": r.operator_confirmed, "error": r.error_message, "date": r.created_at, "phone": r.phone_model, "android": r.android_version, "app": r.app_version, "network": r.network_config}
    return {"gate": audio_gate_status(db), "steps": [{**s, "latest": by_step[s["step"]] or {"status": "not_tested"}} for s in TEST_PLAN]}
