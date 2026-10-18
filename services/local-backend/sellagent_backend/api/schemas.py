"""Pydantic request/response schemas for the REST API (OpenAPI is generated from these)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Ok(BaseModel):
    ok: bool = True
    detail: str | None = None


class ErrorBody(BaseModel):
    error: str
    code: str
    request_id: str | None = None
    detail: Any | None = None


# contacts
class ContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_name: str = Field(min_length=1, max_length=200)
    contact_person: str | None = Field(default=None, max_length=200)
    phone: str = Field(min_length=4, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    city: str | None = None
    district: str | None = None
    state: str | None = None
    country: str = "IN"
    source_url: str | None = Field(default=None, max_length=2000)
    source_verification: Literal["unverified", "verified", "rejected"] = "unverified"
    lead_source: str | None = None
    lead_stage: str = "new"
    campaign_id: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    consent_status: Literal["unknown", "granted", "denied", "withdrawn"] = "unknown"
    category: str | None = Field(default="Gym / Fitness", max_length=50)


class ContactPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_name: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    country: str | None = None
    source_url: str | None = None
    source_verification: Literal["unverified", "verified", "rejected"] | None = None
    lead_source: str | None = None
    lead_stage: str | None = None
    campaign_id: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    consent_status: Literal["unknown", "granted", "denied", "withdrawn"] | None = None
    next_followup_at: datetime | None = None
    archived: bool | None = None
    category: str | None = Field(default=None, max_length=50)


class ContactOut(ORMModel):
    id: str
    business_name: str
    contact_person: str | None
    phone_e164: str
    phone_raw: str | None
    email: str | None
    city: str | None
    district: str | None
    state: str | None
    country: str
    source_url: str | None
    source_verification: str
    lead_source: str | None
    lead_stage: str
    campaign_id: str | None
    last_contact_at: datetime | None
    next_followup_at: datetime | None
    notes: str | None
    tags: list[str]
    consent_status: str
    opted_out: bool
    opt_out_reason: str | None
    opted_out_at: datetime | None
    archived: bool
    category: str | None = None
    created_at: datetime
    updated_at: datetime


class Page(BaseModel):
    items: list[Any]
    total: int
    limit: int
    offset: int


class PermissionIn(BaseModel):
    status: Literal["granted", "denied", "withdrawn"]
    source: str = Field(min_length=1, max_length=200)
    evidence: str | None = None
    channel: str = "voice"
    expires_at: datetime | None = None


class PermissionOut(ORMModel):
    id: str
    contact_id: str
    status: str
    channel: str
    source: str
    evidence: str | None
    recorded_by: str
    recorded_at: datetime
    expires_at: datetime | None


class OptOutIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)
    source: str = "operator"


class SuppressionIn(BaseModel):
    phone: str
    reason: str
    note: str | None = None


class SuppressionOut(ORMModel):
    id: str
    phone_e164: str
    reason: str
    note: str | None
    source: str
    contact_id: str | None
    active: bool
    created_at: datetime


class SuppressionLift(BaseModel):
    justification: str = Field(min_length=3)


# import
class ImportMappingIn(BaseModel):
    upload_id: str
    mapping: dict[str, str | None]
    duplicate_policy: Literal["skip", "update", "import_anyway"] = "skip"
    lead_source: str | None = None
    campaign_id: str | None = None


# campaigns
class CampaignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    calling_mode: Literal["human_assisted", "autonomous"] = "human_assisted"
    script_id: str | None = None
    language: Literal["auto", "hi", "en"] = "auto"
    max_calls_per_day: int = Field(default=50, ge=1, le=500)
    max_attempts_per_contact: int = Field(default=3, ge=1, le=10)
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    requires_consent: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    auto_followup: bool = True
    followup_after_days: int = Field(default=2, ge=1, le=60)


class CampaignPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    description: str | None = None
    calling_mode: Literal["human_assisted", "autonomous"] | None = None
    script_id: str | None = None
    language: Literal["auto", "hi", "en"] | None = None
    max_calls_per_day: int | None = Field(default=None, ge=1, le=500)
    max_attempts_per_contact: int | None = Field(default=None, ge=1, le=10)
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    requires_consent: bool | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    auto_followup: bool | None = None
    followup_after_days: int | None = Field(default=None, ge=1, le=60)


class CampaignOut(ORMModel):
    id: str
    name: str
    description: str | None
    status: str
    authorized_by: str | None
    authorized_at: datetime | None
    calling_mode: str
    script_id: str | None
    language: str
    max_calls_per_day: int
    max_attempts_per_contact: int
    quiet_hours_start: str | None
    quiet_hours_end: str | None
    requires_consent: bool
    starts_at: datetime | None
    ends_at: datetime | None
    auto_followup: bool
    followup_after_days: int
    created_at: datetime
    updated_at: datetime


class CampaignTransition(BaseModel):
    status: Literal["draft", "authorized", "active", "paused", "completed", "archived"]


class IdList(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=5000)


# call jobs
class CallJobIn(BaseModel):
    contact_id: str
    campaign_id: str | None = None
    mode: Literal["human_assisted", "autonomous"] | None = None
    route: Literal["manual", "android_companion", "media_gateway"] = "manual"
    scheduled_for: datetime | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
    device_id: str | None = None


class CallJobOut(ORMModel):
    id: str
    contact_id: str
    campaign_id: str | None
    phone_e164: str
    mode: str
    route: str
    status: str
    scheduled_for: datetime | None
    authorized_by: str | None
    eligibility_result: dict[str, Any] | None
    attempt: int
    device_id: str | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CallOutcomeIn(BaseModel):
    outcome: str
    detail: str | None = None
    followup_at: datetime | None = None
    followup_kind: Literal["call", "demo", "email", "human_handoff"] = "call"
    note: str | None = None


class CancelIn(BaseModel):
    reason: str = "operator_cancel"


class EmergencyStopIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)
    activate: bool = True


class TranscriptIn(BaseModel):
    speaker: Literal["agent", "prospect", "operator", "system"]
    text: str = Field(min_length=1, max_length=4000)
    language: str | None = None
    source: Literal["typed", "stt", "tts", "llm"] = "typed"


class ConversationStepIn(BaseModel):
    utterance: str | None = Field(default=None, max_length=4000)
    language: Literal["auto", "hi", "en"] = "auto"
    use_llm: bool = True


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


# followups
class FollowupIn(BaseModel):
    contact_id: str
    due_at: datetime
    kind: Literal["call", "demo", "email", "human_handoff"] = "call"
    note: str | None = None
    call_id: str | None = None


class FollowupOut(ORMModel):
    id: str
    contact_id: str
    call_id: str | None
    due_at: datetime
    kind: str
    status: str
    note: str | None
    completed_at: datetime | None
    created_at: datetime


# knowledge
class KnowledgeIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=200_000)
    category: str = "general"
    language: Literal["en", "hi"] = "en"
    source: str = "manual"
    structured: dict[str, Any] | None = None
    effective_from: datetime | None = None
    expires_at: datetime | None = None


class KnowledgeOut(ORMModel):
    id: str
    title: str
    category: str
    body: str
    language: str
    status: str
    version: int
    supersedes_id: str | None
    source: str
    trusted: bool
    approved_by: str | None
    approved_at: datetime | None
    effective_from: datetime | None
    expires_at: datetime | None
    structured: dict[str, Any] | None
    injection_flags: list[str]
    created_at: datetime
    updated_at: datetime


class KnowledgeApprove(BaseModel):
    acknowledge_flags: bool = False


class KnowledgeReject(BaseModel):
    reason: str = Field(min_length=1)


class KnowledgeSupersede(BaseModel):
    body: str = Field(min_length=1)
    title: str | None = None
    structured: dict[str, Any] | None = None
    expires_at: datetime | None = None


class RetrieveOut(BaseModel):
    ref: str
    document_id: str
    title: str
    category: str
    text: str
    score: float
    structured: dict[str, Any] | None


# devices
class PairingRequestIn(BaseModel):
    pairing_code: str = Field(min_length=6, max_length=12)
    device_name: str = Field(min_length=1, max_length=80)
    device_model: str = Field(min_length=1, max_length=80)
    android_version: str = Field(min_length=1, max_length=40)
    app_version: str = Field(min_length=1, max_length=40)
    device_public_id: str = Field(min_length=8, max_length=128)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class DeviceOut(ORMModel):
    id: str
    device_public_id: str
    name: str
    model: str
    android_version: str
    app_version: str
    status: str
    token_expires_at: datetime | None
    approved_at: datetime | None
    revoked_at: datetime | None
    last_seen_at: datetime | None
    last_ip: str | None
    capabilities: dict[str, Any]
    created_at: datetime


class PairingDecision(BaseModel):
    approve: bool


# audio tests
class AudioTestIn(BaseModel):
    test_id: str = Field(min_length=3, max_length=64)
    step: str = Field(min_length=1, max_length=80)
    direction: Literal["inbound", "outbound", "both", "none"]
    status: Literal["pass", "fail", "blocked", "not_tested"]
    kind: Literal["real_device", "simulated", "automated"] = "real_device"
    device_id: str | None = None
    route: str | None = None
    api_used: str | None = None
    phone_model: str | None = None
    android_version: str | None = None
    app_version: str | None = None
    network_config: str | None = None
    steps_performed: str | None = None
    expected: str | None = None
    actual: str | None = None
    error_message: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    operator_confirmed: bool = False


class AudioTestOut(ORMModel):
    id: str
    test_id: str
    device_id: str | None
    step: str
    direction: str
    status: str
    kind: str
    route: str | None
    api_used: str | None
    phone_model: str | None
    android_version: str | None
    app_version: str | None
    network_config: str | None
    steps_performed: str | None
    expected: str | None
    actual: str | None
    error_message: str | None
    metrics: dict[str, Any]
    evidence: dict[str, Any]
    operator_confirmed: bool
    created_at: datetime


# settings / backup / ai
class SettingPatch(BaseModel):
    values: dict[str, Any]


class BackupIn(BaseModel):
    passphrase: str | None = Field(default=None, min_length=8)


class RestoreIn(BaseModel):
    path: str
    passphrase: str | None = None
    confirm: Literal["RESTORE"]


class ChatTestIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    language: Literal["auto", "hi", "en"] = "auto"
    max_tokens: int = Field(default=128, ge=1, le=1024)


class TTSIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    language: Literal["hi", "en"] = "en"


class ModelPullIn(BaseModel):
    model: str = Field(min_length=1, max_length=100)
    acknowledge_download: bool = False
    acknowledge_license: bool = False
