"""Audio feasibility test records. Real-device results arrive from the diagnostic APK over the WebSocket; the
operator confirms each on Windows; only confirmed real-device PASS rows can open the release gate."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_area
from sellagent_backend.api.schemas import AudioTestIn, AudioTestOut, Ok
from sellagent_backend.api.v1.errors import conflict, not_found
from sellagent_backend.db.models import AudioTest
from sellagent_backend.services import audit, settings_service
from sellagent_backend.telecom import audio_gate_status
from sellagent_backend.telecom.android import (
    INBOUND_STEP,
    OUTBOUND_STEP,
    digital_injection_proven,
    remote_capture_proven,
)

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
    {"step": "platform_api_support", "direction": "none", "title": "F. Call-audio access via public Android API, authorised OEM integration or documented carrier interface"},
    {"step": "jio_number_retention", "direction": "none", "title": "G. Existing Jio number kept for outbound caller ID and inbound calls"},
]


def _check_confirmable(row: AudioTest) -> None:
    if row.step == INBOUND_STEP and row.status == "pass" and not remote_capture_proven(row):
        raise conflict(
            "Remote speech capture cannot be confirmed as PASS: the phone's probe did not report that a call-audio "
            "source opened (remote_capture_possible is not true). A normal Android app is not expected to hear the "
            "other party; mark this step Blocked on the phone.",
            code="remote_capture_unproven",
        )
    if row.step == OUTBOUND_STEP and row.status == "pass" and not digital_injection_proven(row):
        raise conflict(
            "Generated speech transmission cannot be confirmed as PASS: it must reach the call through a verified "
            "digital uplink (evidence.uplink_injection = digital). Speech played through a loudspeaker into the phone's "
            "microphone is an acoustic relay and does not count; mark this step Blocked on the phone.",
            code="digital_injection_unproven",
        )


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
    if row.operator_confirmed:
        _check_confirmable(row)
    db.add(row)
    db.flush()
    audit.record(db, "audio_test.record", entity_type="audio_test", entity_id=row.id, severity="warning" if body.status == "pass" and body.kind == "real_device" else "info", data={"step": body.step, "status": body.status, "kind": body.kind})
    return row


@router.post("/{row_id}/confirm", response_model=AudioTestOut)
def confirm(row_id: str, db: Session = Depends(get_db), confirmed: bool = True) -> AudioTest:
    row = db.get(AudioTest, row_id)
    if row is None:
        raise not_found("audio test not found")
    if confirmed:
        _check_confirmable(row)
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
