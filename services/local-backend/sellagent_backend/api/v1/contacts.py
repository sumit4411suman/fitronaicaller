from __future__ import annotations

import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_area
from sellagent_backend.api.schemas import (
    ContactIn,
    ContactOut,
    ContactPatch,
    ImportMappingIn,
    Ok,
    OptOutIn,
    Page,
    PermissionIn,
    PermissionOut,
    SuppressionIn,
    SuppressionLift,
    SuppressionOut,
)
from sellagent_backend.api.v1.errors import bad_request, conflict, not_found
from sellagent_backend.db.models import Contact, ContactPermission
from sellagent_backend.services import contacts as svc
from sellagent_backend.services import import_export, suppression
from sellagent_backend.services.contacts import ContactError, DuplicateContact
from sellagent_backend.services.phone import PhoneError

router = APIRouter(prefix="/contacts", tags=["contacts"], dependencies=[Depends(require_area("contacts"))])
sup_router = APIRouter(prefix="/suppression", tags=["suppression"], dependencies=[Depends(require_area("suppression"))])


@router.get("", response_model=Page)
def list_contacts(
    db: Session = Depends(get_db), q: str | None = None, lead_stage: str | None = None, city: str | None = None, campaign_id: str | None = None,
    consent_status: str | None = None, opted_out: bool | None = None, archived: bool | None = False, tag: str | None = None,
    sort: str = "updated_at", desc: bool = True, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
) -> Page:
    rows, total = svc.search(db, q=q, lead_stage=lead_stage, city=city, campaign_id=campaign_id, consent_status=consent_status, opted_out=opted_out, archived=archived, tag=tag, sort=sort, desc=desc, limit=limit, offset=offset)
    return Page(items=[ContactOut.model_validate(c) for c in rows], total=total, limit=limit, offset=offset)


@router.post("", response_model=ContactOut, status_code=201)
def create_contact(body: ContactIn, request: Request, db: Session = Depends(get_db), allow_duplicate: bool = False) -> Contact:
    try:
        return svc.create(db, body.model_dump(), region=request.app.state.settings.default_region, allow_duplicate=allow_duplicate)
    except DuplicateContact as exc:
        raise conflict(str(exc), code="duplicate_contact", existing_id=exc.existing.id) from exc
    except (ContactError, PhoneError) as exc:
        raise bad_request(str(exc)) from exc


@router.get("/stages")
def stages() -> dict:
    return {"lead_stages": list(svc.LEAD_STAGES)}


@router.get("/export")
def export_contacts(db: Session = Depends(get_db), fmt: str = Query("csv", pattern="^(csv|xlsx)$"), archived: bool | None = False, campaign_id: str | None = None) -> StreamingResponse:
    rows, _ = svc.search(db, archived=archived, campaign_id=campaign_id, limit=500, offset=0)
    all_rows: list[Contact] = []
    offset = 0
    while True:
        rows, total = svc.search(db, archived=archived, campaign_id=campaign_id, limit=500, offset=offset)
        all_rows.extend(rows)
        offset += 500
        if offset >= total or not rows:
            break
    if fmt == "xlsx":
        data, media, name = import_export.export_xlsx(all_rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "contacts.xlsx"
    else:
        data, media, name = import_export.export_csv(all_rows), "text/csv; charset=utf-8", "contacts.csv"
    return StreamingResponse(io.BytesIO(data), media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/import/upload")
async def import_upload(request: Request, file: UploadFile = File(...)) -> dict:
    data = await file.read()
    try:
        parsed = import_export.parse_file(file.filename or "upload.csv", data)
    except import_export.ImportError_ as exc:
        raise bad_request(str(exc), code="import_error") from exc
    upload_id = uuid.uuid4().hex
    request.app.state.uploads[upload_id] = parsed
    return {"upload_id": upload_id, "headers": parsed.headers, "row_count": len(parsed.rows), "sample_rows": parsed.rows[:5], "suggested_mapping": parsed.suggested_mapping, "importable_fields": list(import_export.IMPORTABLE_FIELDS), "required_fields": list(import_export.REQUIRED_FIELDS)}


@router.post("/import/preview")
def import_preview(body: ImportMappingIn, request: Request, db: Session = Depends(get_db), limit: int = Query(200, ge=1, le=5000)) -> dict:
    parsed = request.app.state.uploads.get(body.upload_id)
    if parsed is None:
        raise not_found("upload not found or expired")
    try:
        pv = import_export.preview(db, parsed, body.mapping, region=request.app.state.settings.default_region)
    except import_export.ImportError_ as exc:
        raise bad_request(str(exc), code="import_error") from exc
    return {"total_rows": pv.total_rows, "valid": pv.valid, "invalid": pv.invalid, "duplicates": pv.duplicates, "rows": [r.__dict__ for r in pv.rows[:limit]]}


@router.post("/import/commit")
def import_commit(body: ImportMappingIn, request: Request, db: Session = Depends(get_db)) -> dict:
    parsed = request.app.state.uploads.get(body.upload_id)
    if parsed is None:
        raise not_found("upload not found or expired")
    try:
        result = import_export.commit(db, parsed, body.mapping, duplicate_policy=body.duplicate_policy, lead_source=body.lead_source, campaign_id=body.campaign_id, region=request.app.state.settings.default_region)
    except (import_export.ImportError_, ContactError, PhoneError) as exc:
        raise bad_request(str(exc), code="import_error") from exc
    request.app.state.uploads.pop(body.upload_id, None)
    return result


@router.get("/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: str, db: Session = Depends(get_db)) -> Contact:
    c = db.get(Contact, contact_id)
    if c is None:
        raise not_found("contact not found")
    return c


@router.patch("/{contact_id}", response_model=ContactOut)
def patch_contact(contact_id: str, body: ContactPatch, request: Request, db: Session = Depends(get_db)) -> Contact:
    data = body.model_dump(exclude_unset=True)
    try:
        return svc.update(db, contact_id, data, region=request.app.state.settings.default_region)
    except DuplicateContact as exc:
        raise conflict(str(exc), code="duplicate_contact", existing_id=exc.existing.id) from exc
    except (ContactError, PhoneError) as exc:
        if "not found" in str(exc):
            raise not_found(str(exc)) from exc
        raise bad_request(str(exc)) from exc


@router.delete("/{contact_id}", response_model=Ok)
def delete_contact(contact_id: str, db: Session = Depends(get_db), hard: bool = False) -> Ok:
    try:
        if hard:
            svc.delete(db, contact_id)
        else:
            svc.archive(db, contact_id, True)
    except ContactError as exc:
        raise not_found(str(exc)) from exc
    return Ok(detail="deleted" if hard else "archived")


@router.post("/{contact_id}/unarchive", response_model=ContactOut)
def unarchive(contact_id: str, db: Session = Depends(get_db)) -> Contact:
    try:
        return svc.archive(db, contact_id, False)
    except ContactError as exc:
        raise not_found(str(exc)) from exc


@router.get("/{contact_id}/permissions", response_model=list[PermissionOut])
def permissions(contact_id: str, db: Session = Depends(get_db)) -> list[ContactPermission]:
    return list(db.scalars(select(ContactPermission).where(ContactPermission.contact_id == contact_id).order_by(ContactPermission.recorded_at.desc())))


@router.post("/{contact_id}/permissions", response_model=PermissionOut, status_code=201)
def add_permission(contact_id: str, body: PermissionIn, db: Session = Depends(get_db)) -> ContactPermission:
    try:
        return svc.record_permission(db, contact_id, status=body.status, source=body.source, evidence=body.evidence, channel=body.channel, expires_at=body.expires_at)
    except ContactError as exc:
        raise (not_found if "not found" in str(exc) else bad_request)(str(exc)) from exc


@router.post("/{contact_id}/opt-out", response_model=ContactOut)
def opt_out(contact_id: str, body: OptOutIn, db: Session = Depends(get_db)) -> Contact:
    try:
        return svc.opt_out(db, contact_id, reason=body.reason, source=body.source)
    except ContactError as exc:
        raise not_found(str(exc)) from exc


@router.get("/{contact_id}/eligibility")
def eligibility_for_contact(contact_id: str, db: Session = Depends(get_db), campaign_id: str | None = None, mode: str = "human_assisted", route: str = "manual") -> dict:
    from sellagent_backend.db.models import Campaign
    from sellagent_backend.services import eligibility

    c = db.get(Contact, contact_id)
    if c is None:
        raise not_found("contact not found")
    camp = db.get(Campaign, campaign_id) if campaign_id else None
    return eligibility.check(db, c, campaign=camp, mode=mode, route=route).to_dict()


@router.get("/{contact_id}/duplicates", response_model=list[ContactOut])
def duplicates(contact_id: str, db: Session = Depends(get_db)) -> list[Contact]:
    c = db.get(Contact, contact_id)
    if c is None:
        raise not_found("contact not found")
    return list(db.scalars(select(Contact).where(Contact.phone_e164 == c.phone_e164, Contact.id != c.id)))


# ---- suppression
@sup_router.get("", response_model=list[SuppressionOut])
def list_suppression(db: Session = Depends(get_db), active_only: bool = True) -> list:
    return suppression.list_entries(db, active_only=active_only)


@sup_router.post("", response_model=SuppressionOut, status_code=201)
def add_suppression(body: SuppressionIn, request: Request, db: Session = Depends(get_db)) -> object:
    try:
        return suppression.add(db, body.phone, body.reason, note=body.note, region=request.app.state.settings.default_region)
    except (ValueError, PhoneError) as exc:
        raise bad_request(str(exc)) from exc


@sup_router.post("/{entry_id}/lift", response_model=Ok)
def lift_suppression(entry_id: str, body: SuppressionLift, db: Session = Depends(get_db)) -> Ok:
    try:
        suppression.remove(db, entry_id, justification=body.justification)
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
    return Ok()


@sup_router.get("/check")
def check_number(phone: str, request: Request, db: Session = Depends(get_db)) -> dict:
    from sellagent_backend.services.phone import normalize

    try:
        e164 = normalize(phone, request.app.state.settings.default_region)
    except PhoneError as exc:
        raise bad_request(str(exc)) from exc
    entry = suppression.is_suppressed(db, e164)
    return {"phone_e164": e164, "suppressed": entry is not None, "reason": entry.reason if entry else None, "checked_at": datetime.now().astimezone().isoformat()}
