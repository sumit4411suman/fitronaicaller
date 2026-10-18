"""One conversation turn for a live call, shared by the operator console (POST /calls/{id}/step) and the
acoustic AI bridge. Safety facts (consent, opt-out, emergency stop) come from the database, never from the model."""

from __future__ import annotations

from typing import Any

from sellagent_ai.conversation import (
    ConversationContext,
    ConversationEngine,
    ConversationStateMachine,
    InvalidTransition,
    KnowledgeFact,
    State,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sellagent_backend.db.models import AIRun, Call, CallEvent, CallJob, Contact, Transcript
from sellagent_backend.services import call_jobs as svc
from sellagent_backend.services import contacts as contacts_svc
from sellagent_backend.services import settings_service


class ConversationStepError(RuntimeError):
    def __init__(self, msg: str, code: str = "conversation_error") -> None:
        super().__init__(msg)
        self.code = code


def load_state_machine(call: Call) -> ConversationStateMachine:
    try:
        return ConversationStateMachine(State(call.conversation_state))
    except ValueError:
        return ConversationStateMachine(State.CONNECTED)


def facts_for(db: Session, query: str) -> list[KnowledgeFact]:
    from sellagent_kb import retrieve
    from sellagent_kb.service import approved_facts

    facts: dict[str, KnowledgeFact] = {}
    for d in approved_facts(db, "pricing") + approved_facts(db, "product") + approved_facts(db, "compliance"):
        facts[d.id] = KnowledgeFact(f"kb:{d.id}#v{d.version}", d.title, d.category, d.body, d.structured)
    for r in retrieve(db, query or "FITRON price", limit=4):
        facts.setdefault(r.document_id, KnowledgeFact(r.ref, r.title, r.category, r.text, r.structured))
    return list(facts.values())


def next_seq(db: Session, call_id: str) -> int:
    return (db.scalar(select(func.max(Transcript.seq)).where(Transcript.call_id == call_id)) or 0) + 1


def run_step(
    db: Session, c: Call, utterance: str | None, *, engine: ConversationEngine, language: str = "auto",
    prospect_source: str = "typed", agent_source: str | None = None, actor: str = "operator",
) -> dict[str, Any]:
    contact = db.get(Contact, c.contact_id)
    if contact is None:
        raise ConversationStepError("contact not found", "not_found")
    sm = load_state_machine(c)
    if not sm.is_live:
        raise ConversationStepError(f"call is not live (state {sm.state})", "not_live")
    ctx = ConversationContext(consent_ok=contact.consent_status == "granted", emergency_stop=bool(settings_service.get(db, "calling.emergency_stop_active")), opted_out=contact.opted_out, authorized=True)
    seq = next_seq(db, c.id)
    turn_sentiment = None
    if utterance:
        from sellagent_ai.sentiment import analyze

        turn_sentiment = analyze(utterance)
        db.add(Transcript(call_id=c.id, seq=seq, speaker="prospect", text=utterance, source=prospect_source, sentiment=turn_sentiment.label))
        seq += 1
    facts = facts_for(db, utterance or "")
    try:
        turn = engine.respond(sm, utterance, facts=facts, ctx=ctx, preferred_language=language if language != "auto" else settings_service.get(db, "ai.language"), contact_person=contact.contact_person or "", business_name=contact.business_name)
    except InvalidTransition as exc:
        raise ConversationStepError(str(exc), "invalid_transition") from exc
    prev = c.conversation_state
    c.conversation_state = sm.state.value
    c.language = turn.language
    db.add(CallEvent(call_id=c.id, event_type="conversation.step", from_state=prev, to_state=sm.state.value, source="bridge" if actor == "ai_bridge" else "backend", data={"source": turn.source, "guardrail": turn.guardrail.to_dict() if turn.guardrail else None, "llm": turn.llm_metrics}))
    if turn.agent_text:
        db.add(Transcript(call_id=c.id, seq=seq, speaker="agent", text=turn.agent_text, language=turn.language, source=agent_source or ("llm" if turn.source == "llm" else "typed"), knowledge_refs=turn.knowledge_refs))
    if turn.llm_metrics:
        db.add(AIRun(kind="llm", provider=turn.llm_metrics.get("provider", "?"), model=turn.llm_metrics.get("model", "?"), call_id=c.id, first_token_ms=turn.llm_metrics.get("first_token_ms"), total_ms=turn.llm_metrics.get("total_ms"), tokens_per_second=turn.llm_metrics.get("tokens_per_second"), knowledge_refs=turn.knowledge_refs, guardrail_result=turn.guardrail.to_dict() if turn.guardrail else None, success=True))
    if sm.state == State.OPTED_OUT and not contact.opted_out:
        contacts_svc.opt_out(db, contact.id, reason="requested during call", source=f"call:{c.id}")
    if sm.is_terminal and c.outcome is None:
        job = db.get(CallJob, c.call_job_id)
        if job and job.status not in ("completed", "failed", "cancelled"):
            svc.complete(db, job.id, outcome=turn.outcome or ("opted_out" if sm.state == State.OPTED_OUT else "callback_requested"), actor=actor)
    if turn_sentiment is not None:
        from sellagent_ai.sentiment import overall

        labels = list(db.scalars(select(Transcript.sentiment).where(Transcript.call_id == c.id, Transcript.speaker == "prospect")))
        c.sentiment = overall([*labels, turn_sentiment.label])
    return {"sentiment": turn_sentiment.label if turn_sentiment else None, "call_sentiment": c.sentiment, "state": sm.state.value, "agent_text": turn.agent_text, "language": turn.language, "knowledge_refs": turn.knowledge_refs, "source": turn.source, "guardrail": turn.guardrail.to_dict() if turn.guardrail else None, "followup_requested": turn.followup_requested, "outcome": turn.outcome, "terminal": sm.is_terminal, "llm": turn.llm_metrics}
