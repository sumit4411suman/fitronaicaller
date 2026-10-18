"""Deterministic call summary built from the stored transcript, events and outcome (no invented content).
An optional local-LLM summary can be added by the AI worker; it is labelled 'ai_generated' and never spoken."""

from __future__ import annotations

from typing import Any

from sellagent_ai.conversation import ConversationEngine
from sellagent_ai.sentiment import analyze, overall
from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.db.models import Call, CallJob, CallNote, Contact, Followup, Transcript

_POINTS = {
    "price": "Asked about pricing",
    "demo": "Interested in a demo",
    "callback": "Asked to be called later",
    "human": "Asked to speak with a person",
    "opt_out": "Asked not to be called again",
    "negative": "Raised an objection or declined",
    "affirm": "Responded positively",
}


def build(session: Session, call: Call) -> dict[str, Any]:
    tr = list(session.scalars(select(Transcript).where(Transcript.call_id == call.id).order_by(Transcript.seq)))
    prospect = [t for t in tr if t.speaker == "prospect"]
    intents: list[str] = []
    for t in prospect:
        it = ConversationEngine.classify_intent(t.text)
        if it in _POINTS and it not in intents:
            intents.append(it)
    sentiments = [t.sentiment or analyze(t.text).label for t in prospect]
    refs = sorted({r for t in tr for r in (t.knowledge_refs or [])})
    nxt = session.scalar(select(Followup).where(Followup.call_id == call.id).order_by(Followup.due_at))
    notes = [n.body for n in session.scalars(select(CallNote).where(CallNote.call_id == call.id).order_by(CallNote.created_at))]
    contact = session.get(Contact, call.contact_id)
    job = session.get(CallJob, call.call_job_id)
    return {
        "call_id": call.id,
        "contact": {"id": contact.id, "business_name": contact.business_name, "phone_e164": contact.phone_e164} if contact else None,
        "started_at": call.started_at, "ended_at": call.ended_at, "duration_seconds": call.duration_seconds,
        "result": call.outcome, "result_detail": call.outcome_detail, "mode": job.mode if job else None,
        "language": call.language,
        "sentiment": overall(sentiments), "sentiment_by_turn": sentiments,
        "key_points": [_POINTS[i] for i in intents],
        "knowledge_used": refs,
        "next_action": {"kind": nxt.kind, "due_at": nxt.due_at, "status": nxt.status, "note": nxt.note} if nxt else None,
        "notes": notes,
        "turns": {"prospect": len(prospect), "agent": sum(1 for t in tr if t.speaker == "agent"), "total": len(tr)},
        "source": "deterministic (transcript + outcome)",
    }
