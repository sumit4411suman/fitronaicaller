"""SQLAlchemy 2.x ORM models. UTC timestamps throughout (naive ISO strings would lose tz, so we
store timezone-aware datetimes; SQLite stores them as text and SQLAlchemy restores tz info via the
``TZDateTime`` decorator below)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy import JSON as SA_JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sellagent_backend.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex


class TZDateTime(TypeDecorator[datetime]):
    """Store aware datetimes as UTC and always return aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime rejected; use timezone-aware UTC datetimes")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow, nullable=False)


# --------------------------------------------------------------------------- contacts


class Contact(TimestampMixin, Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    business_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_person: Mapped[str | None] = mapped_column(String(200))
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    phone_raw: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(254))
    city: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(2), default="IN", nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    source_verification: Mapped[str] = mapped_column(String(20), default="unverified", nullable=False)
    lead_source: Mapped[str | None] = mapped_column(String(100))
    lead_stage: Mapped[str] = mapped_column(String(30), default="new", nullable=False)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    last_contact_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    next_followup_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(SA_JSON, default=list, nullable=False)
    consent_status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    opt_out_reason: Mapped[str | None] = mapped_column(String(200))
    opted_out_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    permissions: Mapped[list[ContactPermission]] = relationship(back_populates="contact", cascade="all, delete-orphan")
    campaign: Mapped[Campaign | None] = relationship(back_populates="contacts", foreign_keys=[campaign_id])

    __table_args__ = (
        Index("ix_contacts_phone_e164", "phone_e164"),
        Index("ix_contacts_business_name", "business_name"),
        Index("ix_contacts_lead_stage", "lead_stage"),
        Index("ix_contacts_archived", "archived"),
        Index("ix_contacts_next_followup_at", "next_followup_at"),
        CheckConstraint(
            "source_verification IN ('unverified','verified','rejected')", name="ck_contacts_source_verification"
        ),
        CheckConstraint("consent_status IN ('unknown','granted','denied','withdrawn')", name="ck_contacts_consent"),
    )


class ContactPermission(TimestampMixin, Base):
    __tablename__ = "contact_permissions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # granted | denied | withdrawn
    channel: Mapped[str] = mapped_column(String(20), default="voice", nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)  # e.g. "web form", "existing customer"
    evidence: Mapped[str | None] = mapped_column(Text)  # free text / URL / document ref
    recorded_by: Mapped[str] = mapped_column(String(100), default="operator", nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    contact: Mapped[Contact] = relationship(back_populates="permissions")

    __table_args__ = (
        Index("ix_contact_permissions_contact_id", "contact_id"),
        CheckConstraint("status IN ('granted','denied','withdrawn')", name="ck_contact_permissions_status"),
    )


class SuppressionEntry(TimestampMixin, Base):
    __tablename__ = "suppression_list"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)  # opt_out | dnd | complaint | manual | invalid
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100), default="operator", nullable=False)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# --------------------------------------------------------------------------- campaigns


class Campaign(TimestampMixin, Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # draft|authorized|active|paused|completed|archived
    authorized_by: Mapped[str | None] = mapped_column(String(100))
    authorized_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    calling_mode: Mapped[str] = mapped_column(String(20), default="human_assisted", nullable=False)
    script_id: Mapped[str | None] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(5), default="auto", nullable=False)
    max_calls_per_day: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    max_attempts_per_contact: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    quiet_hours_start: Mapped[str | None] = mapped_column(String(5))
    quiet_hours_end: Mapped[str | None] = mapped_column(String(5))
    requires_consent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    ends_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    contacts: Mapped[list[Contact]] = relationship(back_populates="campaign", foreign_keys="Contact.campaign_id")
    members: Mapped[list[CampaignContact]] = relationship(back_populates="campaign", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','authorized','active','paused','completed','archived')", name="ck_campaigns_status"
        ),
        CheckConstraint("calling_mode IN ('human_assisted','autonomous')", name="ck_campaigns_mode"),
    )


class CampaignContact(TimestampMixin, Base):
    __tablename__ = "campaign_contacts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|queued|called|done|excluded
    eligibility_snapshot: Mapped[dict[str, Any] | None] = mapped_column(SA_JSON)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_outcome: Mapped[str | None] = mapped_column(String(50))

    campaign: Mapped[Campaign] = relationship(back_populates="members")

    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_id", name="uq_campaign_contact"),
        Index("ix_campaign_contacts_status", "status"),
    )


# --------------------------------------------------------------------------- calls


class CallJob(TimestampMixin, Base):
    __tablename__ = "call_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="human_assisted", nullable=False)
    route: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)  # manual | android_companion
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(TZDateTime)
    authorized_by: Mapped[str | None] = mapped_column(String(100))
    eligibility_result: Mapped[dict[str, Any] | None] = mapped_column(SA_JSON)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("paired_devices.id", ondelete="SET NULL"))
    authorization_token_hash: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    __table_args__ = (
        Index("ix_call_jobs_status", "status"),
        Index("ix_call_jobs_contact_id", "contact_id"),
        Index("ix_call_jobs_scheduled_for", "scheduled_for"),
        CheckConstraint(
            "status IN ('pending','blocked','queued','dispatched','in_progress','completed','failed','cancelled')",
            name="ck_call_jobs_status",
        ),
    )


class Call(TimestampMixin, Base):
    __tablename__ = "calls"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    call_job_id: Mapped[str] = mapped_column(ForeignKey("call_jobs.id", ondelete="CASCADE"), nullable=False)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), default="outbound", nullable=False)
    conversation_state: Mapped[str] = mapped_column(String(40), default="eligibility_check", nullable=False)
    language: Mapped[str] = mapped_column(String(5), default="auto", nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(40))
    outcome_detail: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    connected_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    audio_route: Mapped[str | None] = mapped_column(String(20))
    recording_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recorded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    events: Mapped[list[CallEvent]] = relationship(back_populates="call", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_calls_contact_id", "contact_id"), Index("ix_calls_outcome", "outcome"))


class CallEvent(Base):
    __tablename__ = "call_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(40))
    to_state: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(30), default="backend", nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict[str, Any] | None] = mapped_column(SA_JSON)

    call: Mapped[Call] = relationship(back_populates="events")

    __table_args__ = (
        Index("ix_call_events_call_id", "call_id"),
        UniqueConstraint("call_id", "message_id", name="uq_call_events_message"),
    )


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(String(10), nullable=False)  # agent | prospect | operator | system
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(5))
    confidence: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="typed", nullable=False)  # typed | stt | tts | llm
    knowledge_refs: Mapped[list[str] | None] = mapped_column(SA_JSON)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("call_id", "seq", name="uq_transcripts_seq"),)


class CallNote(TimestampMixin, Base):
    __tablename__ = "call_notes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    call_id: Mapped[str | None] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    author: Mapped[str] = mapped_column(String(100), default="operator", nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("ix_call_notes_contact_id", "contact_id"),)


class Followup(TimestampMixin, Base):
    __tablename__ = "followups"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    call_id: Mapped[str | None] = mapped_column(ForeignKey("calls.id", ondelete="SET NULL"))
    due_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), default="call", nullable=False)  # call | demo | email | human_handoff
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open | done | cancelled
    note: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    __table_args__ = (Index("ix_followups_due_at", "due_at"), Index("ix_followups_status", "status"))


# --------------------------------------------------------------------------- knowledge


class KnowledgeDocument(TimestampMixin, Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="general", nullable=False)  # pricing|offer|product|faq|objection|general
    body: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending_review", nullable=False)  # pending_review|approved|rejected|expired|superseded
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    supersedes_id: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(200), default="manual", nullable=False)
    trusted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(100))
    approved_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    effective_from: Mapped[datetime | None] = mapped_column(TZDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    structured: Mapped[dict[str, Any] | None] = mapped_column(SA_JSON)  # e.g. {"price_inr": 1999, "period": "month"}
    injection_flags: Mapped[list[str]] = mapped_column(SA_JSON, default=list, nullable=False)

    chunks: Mapped[list[KnowledgeChunk]] = relationship(back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_knowledge_documents_status", "status"),
        Index("ix_knowledge_documents_category", "category"),
        CheckConstraint(
            "status IN ('pending_review','approved','rejected','expired','superseded')", name="ck_kd_status"
        ),
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")

    __table_args__ = (UniqueConstraint("document_id", "seq", name="uq_knowledge_chunks_seq"),)


class AIRun(Base):
    __tablename__ = "ai_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # llm | stt | tts | retrieval | benchmark
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    call_id: Mapped[str | None] = mapped_column(ForeignKey("calls.id", ondelete="SET NULL"))
    prompt_chars: Mapped[int | None] = mapped_column(Integer)
    output_chars: Mapped[int | None] = mapped_column(Integer)
    first_token_ms: Mapped[float | None] = mapped_column(Float)
    total_ms: Mapped[float | None] = mapped_column(Float)
    tokens_per_second: Mapped[float | None] = mapped_column(Float)
    rss_mb: Mapped[float | None] = mapped_column(Float)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    knowledge_refs: Mapped[list[str] | None] = mapped_column(SA_JSON)
    guardrail_result: Mapped[dict[str, Any] | None] = mapped_column(SA_JSON)
    offline: Mapped[bool | None] = mapped_column(Boolean)


# --------------------------------------------------------------------------- devices / audio tests


class PairedDevice(TimestampMixin, Base):
    __tablename__ = "paired_devices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    device_public_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    android_version: Mapped[str] = mapped_column(String(40), nullable=False)
    app_version: Mapped[str] = mapped_column(String(40), nullable=False)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|approved|revoked
    approved_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    last_seen_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    last_ip: Mapped[str | None] = mapped_column(String(45))
    capabilities: Mapped[dict[str, Any]] = mapped_column(SA_JSON, default=dict, nullable=False)

    __table_args__ = (CheckConstraint("status IN ('pending','approved','revoked')", name="ck_paired_devices_status"),)


class AudioTest(TimestampMixin, Base):
    __tablename__ = "audio_tests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    test_id: Mapped[str] = mapped_column(String(64), nullable=False)  # human-readable, e.g. AFT-2026-10-16-01
    device_id: Mapped[str | None] = mapped_column(ForeignKey("paired_devices.id", ondelete="SET NULL"))
    step: Mapped[str] = mapped_column(String(80), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)  # pass|fail|blocked|not_tested
    kind: Mapped[str] = mapped_column(String(20), default="real_device", nullable=False)  # real_device|simulated|automated
    route: Mapped[str | None] = mapped_column(String(20))
    api_used: Mapped[str | None] = mapped_column(String(200))
    phone_model: Mapped[str | None] = mapped_column(String(80))
    android_version: Mapped[str | None] = mapped_column(String(40))
    app_version: Mapped[str | None] = mapped_column(String(40))
    network_config: Mapped[str | None] = mapped_column(String(200))
    steps_performed: Mapped[str | None] = mapped_column(Text)
    expected: Mapped[str | None] = mapped_column(Text)
    actual: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict[str, Any]] = mapped_column(SA_JSON, default=dict, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(SA_JSON, default=dict, nullable=False)
    operator_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_audio_tests_test_id", "test_id"),
        CheckConstraint("status IN ('pass','fail','blocked','not_tested')", name="ck_audio_tests_status"),
        CheckConstraint("kind IN ('real_device','simulated','automated')", name="ck_audio_tests_kind"),
    )


# --------------------------------------------------------------------------- settings / audit


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(SA_JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(100), default="system", nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    actor: Mapped[str] = mapped_column(String(100), default="operator", nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(10), default="info", nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict[str, Any] | None] = mapped_column(SA_JSON)

    __table_args__ = (Index("ix_audit_events_action", "action"), Index("ix_audit_events_occurred_at", "occurred_at"))


class SchemaVersion(Base):
    """Application-level schema marker, in addition to Alembic's own version table."""

    __tablename__ = "schema_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    app_version: Mapped[str] = mapped_column(String(20), nullable=False)
