from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_local_auth
from sellagent_backend.api.schemas import (
    CampaignIn,
    CampaignOut,
    CampaignPatch,
    CampaignTransition,
    ContactOut,
    IdList,
)
from sellagent_backend.api.v1.errors import bad_request, not_found
from sellagent_backend.db.models import Campaign
from sellagent_backend.services import campaigns as svc
from sellagent_backend.services import reports
from sellagent_backend.services.campaigns import CampaignError

router = APIRouter(prefix="/campaigns", tags=["campaigns"], dependencies=[Depends(require_local_auth)])


@router.get("", response_model=list[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), status: str | None = None) -> list[Campaign]:
    q = select(Campaign).order_by(Campaign.updated_at.desc())
    if status:
        q = q.where(Campaign.status == status)
    return list(db.scalars(q))


@router.post("", response_model=CampaignOut, status_code=201)
def create_campaign(body: CampaignIn, db: Session = Depends(get_db)) -> Campaign:
    try:
        return svc.create(db, body.model_dump())
    except CampaignError as exc:
        raise bad_request(str(exc)) from exc


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: str, db: Session = Depends(get_db)) -> Campaign:
    c = db.get(Campaign, campaign_id)
    if c is None:
        raise not_found("campaign not found")
    return c


@router.patch("/{campaign_id}", response_model=CampaignOut)
def patch_campaign(campaign_id: str, body: CampaignPatch, db: Session = Depends(get_db)) -> Campaign:
    try:
        return svc.update(db, campaign_id, body.model_dump(exclude_unset=True))
    except CampaignError as exc:
        raise (not_found if "not found" in str(exc) else bad_request)(str(exc)) from exc


@router.post("/{campaign_id}/transition", response_model=CampaignOut)
def transition(campaign_id: str, body: CampaignTransition, db: Session = Depends(get_db)) -> Campaign:
    try:
        return svc.transition(db, campaign_id, body.status)
    except CampaignError as exc:
        raise (not_found if "not found" in str(exc) else bad_request)(str(exc)) from exc


@router.post("/{campaign_id}/contacts")
def add_contacts(campaign_id: str, body: IdList, db: Session = Depends(get_db)) -> dict:
    try:
        return svc.add_contacts(db, campaign_id, body.ids)
    except CampaignError as exc:
        raise not_found(str(exc)) from exc


@router.get("/{campaign_id}/contacts")
def members(campaign_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Campaign, campaign_id) is None:
        raise not_found("campaign not found")
    return [{"membership": {"id": m.id, "status": m.status, "attempts": m.attempts, "last_outcome": m.last_outcome, "eligibility_snapshot": m.eligibility_snapshot}, "contact": ContactOut.model_validate(c).model_dump()} for m, c in svc.members(db, campaign_id)]


@router.get("/{campaign_id}/stats")
def stats(campaign_id: str, db: Session = Depends(get_db)) -> dict:
    if db.get(Campaign, campaign_id) is None:
        raise not_found("campaign not found")
    return {**svc.stats(db, campaign_id), **reports.campaign_report(db, campaign_id)}
