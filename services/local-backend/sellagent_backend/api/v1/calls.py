"""Call jobs, live call console (conversation steps, transcripts, notes, outcomes), call history, emergency stop."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_local_auth
from sellagent_backend.api.schemas import CallJobIn, CallJobOut, CallOutcomeIn, CancelIn, ConversationStepIn, EmergencyStopIn, NoteIn, Ok, Page, TranscriptIn
from sellagent_backend.api.v1.errors import bad_request, not_found
from sellagent_backend.db.models import Call, CallEvent, CallJob, CallNote, Contact, Transcript
from sellagent_backend.services import call_jobs as svc
from sellagent_backend.services import contacts as contacts_svc
from sellagent_backend.services import followups, reports, settings_service
from sellagent_backend.services.call_jobs import CallJobError
from sellagent_ai.conversation import OUTCOMES, ConversationContext, ConversationStateMachine, InvalidTransition, KnowledgeFact, State

router = APIRouter(prefix="/call-jobs", tags=["calls"], dependencies=[Depends(require_local_auth)])
calls_router = APIRouter(prefix="/calls", tags=["calls"], dependencies=[Depends(require_local_auth)])


@router.get("", response_model=Page)
def list_jobs(db: Session = Depends(get_db), status: str | None = None, limit: int = Query(100, ge=1, le=500), offset: int = 0) -> Page:
    q = select(CallJob)
    if status:
        q = q.where(CallJob.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = list(db.scalars(q.order_by(CallJob.created_at.desc()).limit(limit).offset(offset)))
    return Page(items=[CallJobOut.model_validate(j) for j in rows], total=int(total), limit=limit, offset=offset)


@router.get("/routes")
def routes(request: Request) -> dict:
    st = request.app.state
    return {"manual": st.telecom["manual"].capabilities().__dict__, "android_companion": st.telecom["android_companion"].capabilities().__dict__}


@router.post("", response_model=CallJobOut, status_code=201)
def create_job(body: CallJobIn, db: Session = Depends(get_db)) -> CallJob:
    try:
        return svc.create(db, body.contact_id, campaign_id=body.campaign_id, mode=body.mode, route=body.route, scheduled_for=body.scheduled_for, idempotency_key=body.idempotency_key, device_id=body.device_id)
    except CallJobError as exc:
        raise (not_found if "not found" in str(exc) else bad_request)(str(exc), code="call_job_error") from exc


@router.post("/emergency-stop")
async def emergency_stop(body: EmergencyStopIn, request: Request) -> dict:
    hub = request.app.state.hub
    if body.activate:
        cancelled = await hub.emergency_stop(reason=body.reason, issued_by="windows")
        return {"active": True, "cancelled_jobs": cancelled}
    await hub.clear_emergency_stop()
    return {"active": False, "cancelled_jobs": []}


@router.get("/{job_id}", response_model=CallJobOut)
def get_job(job_id: str, db: Session = Depends(get_db)) -> CallJob:
    j = db.get(CallJob, job_id)
    if j is None:
        raise not_found("call job not found")
    return j


@router.post("/{job_id}/queue", response_model=CallJobOut)
def queue_job(job_id: str, db: Session = Depends(get_db)) -> CallJob:
    try:
        return svc.queue(db, job_id)
    except CallJobError as exc:
        raise bad_request(str(exc)) from exc


@router.post("/{job_id}/dispatch")
async def dispatch_job(job_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Authorize and dispatch. Manual route: returns dial instructions for the operator. Android route: sends
    a CallRequest to the paired phone and waits for its acknowledgement."""
    try:
        job, token = svc.dispatch(db, job_id)
    except CallJobError as exc:
        raise bad_request(str(exc), code="call_job_error") from exc
    db.commit()
    contact = db.get(Contact, job.contact_id)
    adapter = request.app.state.telecom[job.route]
    ok, msg = await adapter.dial(call_job_id=job.id, e164=job.phone_e164, display_name=contact.business_name if contact else None, mode=job.mode, authorization_token=token, language=settings_service.get(db, "ai.language"), device_id=job.device_id)
    if not ok:
        svc.fail(db, job.id, reason=msg)
        raise bad_request(msg, code="dispatch_failed")
    if job.route == "manual":
        svc.mark_in_progress(db, job.id, actor="operator")
    call = db.scalar(select(Call).where(Call.call_job_id == job.id).order_by(Call.created_at.desc()))
    return {"job": CallJobOut.model_validate(db.get(CallJob, job.id)).model_dump(), "call_id": call.id if call else None, "route": job.route, "message": msg, "dial_number": job.phone_e164}


@router.post("/{job_id}/cancel", response_model=CallJobOut)
async def cancel_job(job_id: str, body: CancelIn, request: Request, db: Session = Depends(get_db)) -> CallJob:
    try:
        job = svc.cancel(db, job_id, reason=body.reason)
    except CallJobError as exc:
        raise not_found(str(exc)) from exc
    if job.route == "android_companion" and job.device_id:
        await request.app.state.telecom["android_companion"].cancel(call_job_id=job.id, device_id=job.device_id, reason=body.reason)
    return job


# ---------------------------------------------------------------- live console per call
def _call(db: Session, call_id: str) -> Call:
    c = db.get(Call, call_id)
    if c is None:
        raise not_found("call not found")
    return c


def _load_sm(call: Call) -> ConversationStateMachine:
    try:
        return ConversationStateMachine(State(call.conversation_state))
    except ValueError:
        return ConversationStateMachine(State.CONNECTED)


def _facts(db: Session, query: str) -> list[KnowledgeFact]:
    from sellagent_kb import retrieve
    from sellagent_kb.service import approved_facts

    facts: dict[str, KnowledgeFact] = {}
    for d in approved_facts(db, "pricing") + approved_facts(db, "product") + approved_facts(db, "compliance"):
        facts[d.id] = KnowledgeFact(f"kb:{d.id}#v{d.version}", d.title, d.category, d.body, d.structured)
    for r in retrieve(db, query or "FITRON price", limit=4):
        facts.setdefault(r.document_id, KnowledgeFact(r.ref, r.title, r.category, r.text, r.structured))
    return list(facts.values())


@calls_router.get("", response_model=Page)
def history(db: Session = Depends(get_db), contact_id: str | None = None, outcome: str | None = None, limit: int = Query(100, ge=1, le=500), offset: int = 0) -> Page:
    rows, total = reports.call_history(db, limit=limit, offset=offset, contact_id=contact_id, outcome=outcome)
    return Page(items=rows, total=total, limit=limit, offset=offset)


@calls_router.get("/outcomes")
def outcomes() -> dict:
    return {"outcomes": list(OUTCOMES)}


@calls_router.get("/{call_id}")
def get_call(call_id: str, db: Session = Depends(get_db)) -> dict:
    c = _call(db, call_id)
    job = db.get(CallJob, c.call_job_id)
    contact = db.get(Contact, c.contact_id)
    events = list(db.scalars(select(CallEvent).where(CallEvent.call_id == c.id).order_by(CallEvent.occurred_at)))
    tr = list(db.scalars(select(Transcript).where(Transcript.call_id == c.id).order_by(Transcript.seq)))
    notes = list(db.scalars(select(CallNote).where(CallNote.call_id == c.id).order_by(CallNote.created_at)))
    return {
        "call": {"id": c.id, "call_job_id": c.call_job_id, "contact_id": c.contact_id, "conversation_state": c.conversation_state, "language": c.language, "outcome": c.outcome, "outcome_detail": c.outcome_detail, "started_at": c.started_at, "connected_at": c.connected_at, "ended_at": c.ended_at, "duration_seconds": c.duration_seconds, "audio_route": c.audio_route, "recorded": c.recorded},
        "job": CallJobOut.model_validate(job).model_dump() if job else None,
        "contact": contacts_svc.to_dict(contact) if contact else None,
        "events": [{"id": e.id, "occurred_at": e.occurred_at, "event_type": e.event_type, "from_state": e.from_state, "to_state": e.to_state, "source": e.source, "data": e.data} for e in events],
        "transcript": [{"seq": t.seq, "speaker": t.speaker, "text": t.text, "language": t.language, "source": t.source, "knowledge_refs": t.knowledge_refs, "created_at": t.created_at} for t in tr],
        "notes": [{"id": n.id, "author": n.author, "body": n.body, "created_at": n.created_at} for n in notes],
    }


@calls_router.post("/{call_id}/connected")
def mark_connected(call_id: str, db: Session = Depends(get_db)) -> dict:
    """Operator confirms the prospect answered (human-assisted route)."""
    c = _call(db, call_id)
    sm = _load_sm(c)
    path = {
        State.ELIGIBILITY_CHECK: [State.CALL_AUTHORIZATION, State.DIAL_REQUEST, State.DIALING, State.CONNECTED],
        State.CALL_AUTHORIZATION: [State.DIAL_REQUEST, State.DIALING, State.CONNECTED],
        State.DIAL_REQUEST: [State.DIALING, State.CONNECTED], State.DIALING: [State.CONNECTED], State.RINGING: [State.CONNECTED],
    }
    try:
        for nxt in path.get(sm.state, []):
            sm.transition(nxt, reason="operator confirmed answer", ctx=ConversationContext(authorized=True))
    except InvalidTransition as exc:
        raise bad_request(str(exc)) from exc
    if not sm.is_live:
        raise bad_request(f"call cannot be marked connected from state {sm.state}", code="invalid_transition")
    c.conversation_state = sm.state.value
    c.connected_at = c.connected_at or datetime.now(UTC)
    svc.mark_in_progress(db, c.call_job_id, actor="operator")
    db.add(CallEvent(call_id=c.id, event_type="connected", to_state=sm.state.value, source="operator"))
    return {"conversation_state": c.conversation_state}


@calls_router.post("/{call_id}/no-answer")
def mark_no_answer(call_id: str, db: Session = Depends(get_db), busy: bool = False) -> dict:
    c = _call(db, call_id)
    outcome = "busy" if busy else "no_answer"
    c.conversation_state = outcome
    svc.complete(db, c.call_job_id, outcome=outcome, actor="operator")
    return {"outcome": outcome}


@calls_router.post("/{call_id}/step")
def conversation_step(call_id: str, body: ConversationStepIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """Advance the conversation: record the prospect's utterance (if any) and produce the next agent line.
    Safety facts (consent, opt-out, emergency stop) come from the database, never from the model."""
    c = _call(db, call_id)
    contact = db.get(Contact, c.contact_id)
    assert contact is not None
    sm = _load_sm(c)
    if not sm.is_live:
        raise bad_request(f"call is not live (state {sm.state})", code="not_live")
    ctx = ConversationContext(consent_ok=contact.consent_status == "granted", emergency_stop=bool(settings_service.get(db, "calling.emergency_stop_active")), opted_out=contact.opted_out, authorized=True)
    seq = (db.scalar(select(func.max(Transcript.seq)).where(Transcript.call_id == c.id)) or 0) + 1
    if body.utterance:
        db.add(Transcript(call_id=c.id, seq=seq, speaker="prospect", text=body.utterance, source="typed"))
        seq += 1
    engine = request.app.state.conversation_engine(use_llm=body.use_llm)
    facts = _facts(db, body.utterance or "")
    try:
        turn = engine.respond(sm, body.utterance, facts=facts, ctx=ctx, preferred_language=body.language if body.language != "auto" else settings_service.get(db, "ai.language"), contact_person=contact.contact_person or "", business_name=contact.business_name)
    except InvalidTransition as exc:
        raise bad_request(str(exc), code="invalid_transition") from exc
    prev = c.conversation_state
    c.conversation_state = sm.state.value
    c.language = turn.language
    db.add(CallEvent(call_id=c.id, event_type="conversation.step", from_state=prev, to_state=sm.state.value, source="backend", data={"source": turn.source, "guardrail": turn.guardrail.to_dict() if turn.guardrail else None, "llm": turn.llm_metrics}))
    if turn.agent_text:
        db.add(Transcript(call_id=c.id, seq=seq, speaker="agent", text=turn.agent_text, language=turn.language, source="llm" if turn.source == "llm" else "typed", knowledge_refs=turn.knowledge_refs))
    if turn.llm_metrics:
        from sellagent_backend.db.models import AIRun

        db.add(AIRun(kind="llm", provider=turn.llm_metrics.get("provider", "?"), model=turn.llm_metrics.get("model", "?"), call_id=c.id, first_token_ms=turn.llm_metrics.get("first_token_ms"), total_ms=turn.llm_metrics.get("total_ms"), tokens_per_second=turn.llm_metrics.get("tokens_per_second"), knowledge_refs=turn.knowledge_refs, guardrail_result=turn.guardrail.to_dict() if turn.guardrail else None, success=True))
    if sm.state == State.OPTED_OUT and not contact.opted_out:
        contacts_svc.opt_out(db, contact.id, reason="requested during call", source=f"call:{c.id}")
    if sm.is_terminal and c.outcome is None:
        job = db.get(CallJob, c.call_job_id)
        if job and job.status not in ("completed", "failed", "cancelled"):
            svc.complete(db, job.id, outcome=turn.outcome or ("opted_out" if sm.state == State.OPTED_OUT else "callback_requested"), actor="operator")
    return {"state": sm.state.value, "agent_text": turn.agent_text, "language": turn.language, "knowledge_refs": turn.knowledge_refs, "source": turn.source, "guardrail": turn.guardrail.to_dict() if turn.guardrail else None, "followup_requested": turn.followup_requested, "outcome": turn.outcome, "terminal": sm.is_terminal, "llm": turn.llm_metrics}


@calls_router.post("/{call_id}/transcript")
def add_transcript(call_id: str, body: TranscriptIn, db: Session = Depends(get_db)) -> dict:
    c = _call(db, call_id)
    seq = (db.scalar(select(func.max(Transcript.seq)).where(Transcript.call_id == c.id)) or 0) + 1
    db.add(Transcript(call_id=c.id, seq=seq, speaker=body.speaker, text=body.text, language=body.language, source=body.source))
    return {"seq": seq}


@calls_router.post("/{call_id}/notes")
def add_note(call_id: str, body: NoteIn, db: Session = Depends(get_db)) -> dict:
    c = _call(db, call_id)
    n = CallNote(call_id=c.id, contact_id=c.contact_id, body=body.body)
    db.add(n)
    db.flush()
    return {"id": n.id}


@calls_router.post("/{call_id}/outcome")
def set_outcome(call_id: str, body: CallOutcomeIn, db: Session = Depends(get_db)) -> dict:
    c = _call(db, call_id)
    if body.outcome not in OUTCOMES:
        raise bad_request(f"outcome must be one of {OUTCOMES}")
    contact = db.get(Contact, c.contact_id)
    assert contact is not None
    try:
        svc.complete(db, c.call_job_id, outcome=body.outcome, detail=body.detail)
    except CallJobError as exc:
        raise bad_request(str(exc)) from exc
    c.conversation_state = {"opted_out": "opted_out", "no_answer": "no_answer", "busy": "busy", "technical_failure": "technical_failure", "cancelled": "cancelled"}.get(body.outcome, "completed")
    stage = {"converted": "converted", "demo_scheduled": "demo_scheduled", "interested": "interested", "not_interested": "not_interested", "opted_out": "do_not_call", "callback_requested": "contacted", "human_handoff": "contacted"}.get(body.outcome)
    if stage:
        contact.lead_stage = stage
    if body.outcome == "opted_out" and not contact.opted_out:
        contacts_svc.opt_out(db, contact.id, reason=body.detail or "requested during call", source=f"call:{c.id}")
    if body.outcome == "wrong_number":
        from sellagent_backend.services import suppression

        suppression.add(db, contact.phone_e164, "wrong_number", note=body.detail, source=f"call:{c.id}")
    fu = None
    if body.followup_at:
        fu = followups.create(db, contact.id, due_at=body.followup_at, kind=body.followup_kind, note=body.note, call_id=c.id)
    if body.note:
        db.add(CallNote(call_id=c.id, contact_id=c.contact_id, body=body.note))
    return {"outcome": body.outcome, "followup_id": fu.id if fu else None, "lead_stage": contact.lead_stage}


@calls_router.post("/{call_id}/cancel", response_model=Ok)
async def cancel_live(call_id: str, body: CancelIn, request: Request, db: Session = Depends(get_db)) -> Ok:
    c = _call(db, call_id)
    job = svc.cancel(db, c.call_job_id, reason=body.reason)
    c.conversation_state = "cancelled"
    if job.route == "android_companion" and job.device_id:
        await request.app.state.telecom["android_companion"].cancel(call_job_id=job.id, device_id=job.device_id, reason=body.reason)
    return Ok(detail="cancelled")
