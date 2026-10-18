from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from sellagent_backend.db.models import KnowledgeChunk, KnowledgeDocument
from sellagent_backend.services import audit
from sellagent_kb.chunking import chunk_text, estimate_tokens

CATEGORIES = ("pricing", "offer", "product", "faq", "objection", "compliance", "general")

# Patterns that indicate an imported document is trying to instruct the model rather than inform it.
_INJECTION_PATTERNS = [
    r"(ignore|forget|disregard)\s+(?:\w+\s+){0,3}(instructions?|rules?|prompts?|guidelines?)",
    r"you are now",
    r"act as (an?|the) ",
    r"system prompt",
    r"</?\s*(system|assistant|user|instruction|prompt)\s*>",
    r"\[\s*(inst|system)\s*\]",
    r"do not tell the (user|customer|operator)",
    r"(reveal|print|show) (your|the) (prompt|instructions|rules)",
    r"override (consent|suppression|opt[- ]?out|emergency)",
    r"(always|must) (say|claim|promise|guarantee)",
    r"base64",
    r"https?://\S+",  # URLs are flagged for review, not auto-trusted
]
_INJ_RE = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


class KnowledgeError(ValueError):
    pass


@dataclass
class RetrievedChunk:
    document_id: str
    chunk_id: int
    title: str
    category: str
    text: str
    score: float
    version: int
    structured: dict[str, Any] | None

    @property
    def ref(self) -> str:
        return f"kb:{self.document_id}#v{self.version}:c{self.chunk_id}"


def screen_for_injection(body: str) -> list[str]:
    flags: list[str] = []
    for rx in _INJ_RE:
        m = rx.search(body)
        if m:
            flags.append(m.group(0)[:80])
    # zero-width / control characters often used to hide instructions
    if re.search(r"[​-‏‪-‮⁦-⁩]", body):
        flags.append("hidden unicode control characters")
    return flags


def create_document(
    session: Session, *, title: str, body: str, category: str = "general", language: str = "en", source: str = "manual",
    structured: dict[str, Any] | None = None, effective_from: datetime | None = None, expires_at: datetime | None = None,
    actor: str = "operator", trusted: bool = False,
) -> KnowledgeDocument:
    if category not in CATEGORIES:
        raise KnowledgeError(f"category must be one of {CATEGORIES}")
    if not title.strip() or not body.strip():
        raise KnowledgeError("title and body are required")
    if len(body) > 200_000:
        raise KnowledgeError("document too large (200k chars max)")
    flags = screen_for_injection(body)
    doc = KnowledgeDocument(
        title=title.strip(), body=body, category=category, language=language, source=source, structured=structured,
        effective_from=effective_from, expires_at=expires_at, trusted=trusted, injection_flags=flags, status="pending_review",
    )
    session.add(doc)
    session.flush()
    for i, ch in enumerate(chunk_text(body)):
        session.add(KnowledgeChunk(document_id=doc.id, seq=i, text=ch, token_estimate=estimate_tokens(ch)))
    session.flush()
    audit.record(session, "knowledge.create", actor=actor, entity_type="knowledge_document", entity_id=doc.id, data={"category": category, "flags": flags})
    return doc


def approve(session: Session, document_id: str, *, actor: str, acknowledge_flags: bool = False) -> KnowledgeDocument:
    doc = _get(session, document_id)
    if doc.status not in ("pending_review", "rejected"):
        raise KnowledgeError(f"cannot approve a document in status {doc.status}")
    if doc.injection_flags and not acknowledge_flags:
        raise KnowledgeError("document has injection/suspicious-content flags; review and acknowledge them explicitly")
    doc.status, doc.approved_by, doc.approved_at, doc.trusted = "approved", actor, datetime.now(UTC), True
    session.flush()
    audit.record(session, "knowledge.approve", actor=actor, entity_type="knowledge_document", entity_id=doc.id, severity="warning", data={"flags_acknowledged": bool(doc.injection_flags)})
    return doc


def reject(session: Session, document_id: str, *, actor: str, reason: str) -> KnowledgeDocument:
    doc = _get(session, document_id)
    doc.status = "rejected"
    session.flush()
    audit.record(session, "knowledge.reject", actor=actor, entity_type="knowledge_document", entity_id=doc.id, data={"reason": reason})
    return doc


def supersede(session: Session, document_id: str, *, body: str, actor: str, title: str | None = None, structured: dict[str, Any] | None = None, expires_at: datetime | None = None) -> KnowledgeDocument:
    """Create version n+1 as pending review. The old version stays approved until the new one is approved."""
    old = _get(session, document_id)
    new = create_document(session, title=title or old.title, body=body, category=old.category, language=old.language, source=old.source, structured=structured if structured is not None else old.structured, expires_at=expires_at, actor=actor)
    new.version, new.supersedes_id = old.version + 1, old.id
    session.flush()
    return new


def _finalize_supersede(session: Session, doc: KnowledgeDocument) -> None:
    if doc.supersedes_id:
        old = session.get(KnowledgeDocument, doc.supersedes_id)
        if old and old.status == "approved":
            old.status = "superseded"


def expire_outdated(session: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    n = 0
    for doc in session.scalars(select(KnowledgeDocument).where(KnowledgeDocument.status == "approved", KnowledgeDocument.expires_at.is_not(None), KnowledgeDocument.expires_at <= now)):
        doc.status = "expired"
        n += 1
    session.flush()
    return n


def delete(session: Session, document_id: str, *, actor: str) -> None:
    doc = _get(session, document_id)
    session.delete(doc)
    session.flush()
    audit.record(session, "knowledge.delete", actor=actor, entity_type="knowledge_document", entity_id=document_id, severity="warning")


def _fts_query(q: str) -> str:
    terms = [t for t in re.findall(r"[\wऀ-ॿ]+", q) if len(t) > 1]
    if not terms:
        return '""'
    return " OR ".join(f'"{t}"' for t in terms[:12])


def retrieve(session: Session, query: str, *, limit: int = 5, category: str | None = None, now: datetime | None = None, include_unapproved: bool = False) -> list[RetrievedChunk]:
    """Approved, effective, non-expired documents only (unless include_unapproved for operator testing)."""
    now = now or datetime.now(UTC)
    sql = text(
        "SELECT c.id, c.document_id, bm25(knowledge_chunks_fts) AS score FROM knowledge_chunks_fts f "
        "JOIN knowledge_chunks c ON c.id = f.rowid WHERE knowledge_chunks_fts MATCH :q ORDER BY score LIMIT :lim"
    )
    rows = session.execute(sql, {"q": _fts_query(query), "lim": limit * 6}).all()
    out: list[RetrievedChunk] = []
    seen_docs: set[str] = set()
    for chunk_id, doc_id, score in rows:
        doc = session.get(KnowledgeDocument, doc_id)
        if doc is None:
            continue
        if not include_unapproved:
            if doc.status != "approved":
                continue
            if doc.effective_from and doc.effective_from > now:
                continue
            if doc.expires_at and doc.expires_at <= now:
                continue
        if category and doc.category != category:
            continue
        if doc_id in seen_docs:
            continue
        seen_docs.add(doc_id)
        chunk = session.get(KnowledgeChunk, chunk_id)
        assert chunk is not None
        out.append(RetrievedChunk(doc.id, chunk.id, doc.title, doc.category, chunk.text, float(-score), doc.version, doc.structured))
        if len(out) >= limit:
            break
    return out


def approved_facts(session: Session, category: str | None = None) -> list[KnowledgeDocument]:
    q = select(KnowledgeDocument).where(KnowledgeDocument.status == "approved")
    if category:
        q = q.where(KnowledgeDocument.category == category)
    return list(session.scalars(q.order_by(KnowledgeDocument.category, KnowledgeDocument.title)))


def _get(session: Session, document_id: str) -> KnowledgeDocument:
    doc = session.get(KnowledgeDocument, document_id)
    if doc is None:
        raise KnowledgeError("document not found")
    return doc


FITRON_SEED: list[dict[str, Any]] = [
    {
        "title": "What FITRON is",
        "category": "product",
        "approved": True,
        "body": "FITRON is gym accounting software. It is sold as a subscription (SaaS). FITRON helps gym businesses manage their accounting.",
        "body_hi": "FITRON जिम के लिए अकाउंटिंग सॉफ़्टवेयर है। यह सब्सक्रिप्शन (SaaS) के रूप में उपलब्ध है।",
        "structured": {"product": "FITRON", "type": "gym accounting software", "model": "SaaS"},
    },
    {
        "title": "Professional plan list price",
        "category": "pricing",
        "approved": True,
        "body": "The FITRON Professional plan list price is ₹1,999 per month (INR 1999 per month).",
        "body_hi": "FITRON प्रोफेशनल प्लान की लिस्ट प्राइस ₹1,999 प्रति माह है।",
        "structured": {"plan": "Professional", "price_inr": 1999, "period": "month", "currency": "INR"},
    },
    {
        "title": "First-100-customers launch offer (requires approval before use)",
        "category": "offer",
        "approved": False,
        "body": (
            "Launch offer for the first 100 customers: one month free, then a 50% discount on the Professional monthly price. "
            "The discounted monthly price is approximately ₹1,000 after rounding (50% of ₹1,999 = ₹999.50). "
            "Eligibility, exact duration of the discount, start and end dates and full terms must be configured in the structured "
            "fields and approved by an authorized user before the agent may mention this offer."
        ),
        "body_hi": "पहले 100 ग्राहकों के लिए लॉन्च ऑफ़र: एक महीना मुफ़्त और प्रोफेशनल मासिक मूल्य पर 50% छूट (लगभग ₹1,000 प्रति माह)। शर्तें स्वीकृति के बाद ही लागू।",
        "structured": {
            "offer": "first_100_customers", "free_months": 1, "discount_percent": 50, "discounted_price_inr_approx": 1000,
            "base_price_inr": 1999, "discount_duration_months": None, "eligibility": "TO BE CONFIGURED", "starts_on": None, "ends_on": None,
            "terms": "TO BE CONFIGURED AND APPROVED",
        },
    },
    {
        "title": "What the agent must not claim",
        "category": "compliance",
        "approved": True,
        "body": (
            "The assistant has no confirmed information about FITRON features beyond 'gym accounting software', integrations, customer "
            "testimonials, revenue guarantees, support commitments, availability dates or discounts other than approved entries. "
            "When asked about these, say you do not have confirmed information and offer a human follow-up."
        ),
        "structured": {"policy": "no_unapproved_claims"},
    },
]


def seed_fitron_defaults(session: Session, *, actor: str = "system") -> int:
    """Insert the approved starting facts if the knowledge base is empty. Returns number inserted."""
    if session.scalar(select(KnowledgeDocument.id).limit(1)):
        return 0
    n = 0
    for item in FITRON_SEED:
        for lang in ("en", "hi"):
            body = item["body"] if lang == "en" else item.get("body_hi")
            if not body:
                continue
            doc = create_document(session, title=item["title"] + (" (हिन्दी)" if lang == "hi" else ""), body=body, category=item["category"], language=lang, source="fitron_seed", structured=item.get("structured"), actor=actor, trusted=True)
            if item["approved"]:
                approve(session, doc.id, actor=actor)
            n += 1
    return n
