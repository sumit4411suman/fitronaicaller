"""CSV/XLSX import with preview, field mapping, validation, duplicate handling and a single
transaction per commit; plus CSV/XLSX export."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from sqlalchemy.orm import Session

from sellagent_backend.db.models import Contact
from sellagent_backend.services import audit, contacts
from sellagent_backend.services.contacts import DuplicateContact
from sellagent_backend.services.phone import PhoneError, normalize

IMPORTABLE_FIELDS = (
    "business_name", "contact_person", "phone", "email", "city", "district", "state", "country", "source_url",
    "lead_source", "lead_stage", "notes", "tags", "consent_status",
)
REQUIRED_FIELDS = ("business_name", "phone")
MAX_ROWS = 50_000
MAX_FILE_BYTES = 25 * 1024 * 1024

_ALIASES = {
    "business_name": {"business", "gym", "gym name", "business name", "name", "company"},
    "contact_person": {"contact", "owner", "person", "contact person", "contact name"},
    "phone": {"phone", "mobile", "telephone", "number", "phone number", "mobile number", "contact number"},
    "email": {"email", "e-mail", "mail"},
    "city": {"city", "town"},
    "district": {"district"},
    "state": {"state", "province"},
    "country": {"country"},
    "source_url": {"url", "source url", "website", "link", "source"},
    "lead_source": {"lead source", "source type"},
    "lead_stage": {"stage", "lead stage", "status"},
    "notes": {"notes", "note", "remarks", "comment"},
    "tags": {"tags", "tag", "labels"},
    "consent_status": {"consent", "consent status", "permission"},
}


class ImportError_(ValueError):
    pass


@dataclass
class ParsedFile:
    headers: list[str]
    rows: list[list[str]]
    suggested_mapping: dict[str, str | None]  # target_field -> source header


@dataclass
class RowResult:
    row_number: int
    status: str  # ok | invalid | duplicate
    normalized: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duplicate_of: str | None = None


@dataclass
class ImportPreview:
    total_rows: int
    valid: int
    invalid: int
    duplicates: int
    rows: list[RowResult]


def _sniff_csv(text: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        return csv.excel  # type: ignore[return-value]


def parse_file(filename: str, data: bytes) -> ParsedFile:
    if len(data) > MAX_FILE_BYTES:
        raise ImportError_("file larger than 25 MB")
    ext = Path(filename).suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:
            raise ImportError_(f"could not read workbook: {exc}") from exc
        ws = wb.active
        if ws is None:
            raise ImportError_("workbook has no active sheet")
        it = ws.iter_rows(values_only=True)
        try:
            headers = [str(h).strip() if h is not None else "" for h in next(it)]
        except StopIteration as exc:
            raise ImportError_("workbook is empty") from exc
        rows: list[list[str]] = []
        for r in it:
            if r is None or all(v in (None, "") for v in r):
                continue
            rows.append(["" if v is None else (v.isoformat() if isinstance(v, datetime) else str(v)).strip() for v in r])
            if len(rows) > MAX_ROWS:
                raise ImportError_(f"more than {MAX_ROWS} rows")
    elif ext in (".csv", ".txt"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        text = text.replace("\x00", "")
        reader = csv.reader(io.StringIO(text), dialect=_sniff_csv(text))
        try:
            headers = [h.strip() for h in next(reader)]
        except StopIteration as exc:
            raise ImportError_("CSV file is empty") from exc
        rows = []
        for r in reader:
            if not any(cell.strip() for cell in r):
                continue
            rows.append([c.strip() for c in r])
            if len(rows) > MAX_ROWS:
                raise ImportError_(f"more than {MAX_ROWS} rows")
    else:
        raise ImportError_("unsupported file type; use .csv or .xlsx")
    if not any(headers):
        raise ImportError_("header row is empty")
    return ParsedFile(headers=headers, rows=rows, suggested_mapping=suggest_mapping(headers))


def suggest_mapping(headers: list[str]) -> dict[str, str | None]:
    lower = {h.lower().strip(): h for h in headers}
    mapping: dict[str, str | None] = {}
    used: set[str] = set()
    for target in IMPORTABLE_FIELDS:
        found = None
        for alias in sorted(_ALIASES[target], key=len, reverse=True):
            if alias in lower and lower[alias] not in used:
                found = lower[alias]
                break
        mapping[target] = found
        if found:
            used.add(found)
    return mapping


def _sanitize_cell(v: str) -> str:
    # Neutralise spreadsheet formula injection on later export and strip control chars
    v = "".join(ch for ch in v if ch == "\t" or ch >= " ")
    return v.strip()


def build_rows(parsed: ParsedFile, mapping: dict[str, str | None]) -> list[dict[str, Any]]:
    for req in REQUIRED_FIELDS:
        if not mapping.get(req):
            raise ImportError_(f"required field {req!r} is not mapped")
    idx = {h: i for i, h in enumerate(parsed.headers)}
    out: list[dict[str, Any]] = []
    for r in parsed.rows:
        rec: dict[str, Any] = {}
        for target, src in mapping.items():
            if not src or src not in idx:
                continue
            val = _sanitize_cell(r[idx[src]]) if idx[src] < len(r) else ""
            if target == "tags":
                rec[target] = [t.strip() for t in val.split(",") if t.strip()]
            elif val != "":
                rec[target] = val
        out.append(rec)
    return out


def preview(session: Session, parsed: ParsedFile, mapping: dict[str, str | None], *, region: str = "IN") -> ImportPreview:
    records = build_rows(parsed, mapping)
    results: list[RowResult] = []
    seen_phones: dict[str, int] = {}
    for i, rec in enumerate(records, start=2):  # header is row 1
        rr = RowResult(row_number=i, status="ok")
        if not rec.get("business_name"):
            rr.errors.append("business_name missing")
        try:
            e164 = normalize(rec.get("phone", ""), region)
            rec["phone_e164"] = e164
        except PhoneError as exc:
            rr.errors.append(str(exc))
            e164 = None
        if rec.get("lead_stage") and rec["lead_stage"] not in contacts.LEAD_STAGES:
            rr.errors.append(f"invalid lead_stage {rec['lead_stage']!r}")
        if rec.get("consent_status") and rec["consent_status"] not in ("unknown", "granted", "denied", "withdrawn"):
            rr.errors.append("invalid consent_status")
        if rr.errors:
            rr.status = "invalid"
        elif e164:
            if e164 in seen_phones:
                rr.status, rr.duplicate_of = "duplicate", f"row {seen_phones[e164]}"
            else:
                seen_phones[e164] = i
                dup = contacts.find_duplicate(session, e164, rec.get("business_name"))
                if dup:
                    rr.status, rr.duplicate_of = "duplicate", dup.id
        rr.normalized = rec
        results.append(rr)
    return ImportPreview(
        total_rows=len(results),
        valid=sum(1 for r in results if r.status == "ok"),
        invalid=sum(1 for r in results if r.status == "invalid"),
        duplicates=sum(1 for r in results if r.status == "duplicate"),
        rows=results,
    )


def commit(
    session: Session, parsed: ParsedFile, mapping: dict[str, str | None], *, duplicate_policy: str = "skip",
    lead_source: str | None = None, campaign_id: str | None = None, actor: str = "operator", region: str = "IN",
) -> dict[str, int]:
    """Writes all valid rows in the caller's transaction. ``duplicate_policy``: skip | update | import_anyway.
    Any unexpected error rolls back everything (the caller's session_scope handles rollback)."""
    if duplicate_policy not in ("skip", "update", "import_anyway"):
        raise ImportError_("duplicate_policy must be skip, update or import_anyway")
    pv = preview(session, parsed, mapping, region=region)
    created = updated = skipped = invalid = 0
    with session.begin_nested():
        for rr in pv.rows:
            if rr.status == "invalid":
                invalid += 1
                continue
            rec = dict(rr.normalized)
            if lead_source and not rec.get("lead_source"):
                rec["lead_source"] = lead_source
            if campaign_id:
                rec["campaign_id"] = campaign_id
            if rr.status == "duplicate":
                if duplicate_policy == "skip" or rr.duplicate_of is None or rr.duplicate_of.startswith("row "):
                    skipped += 1
                    continue
                if duplicate_policy == "update":
                    upd = {k: v for k, v in rec.items() if k not in ("phone", "phone_e164") and v not in (None, "", [])}
                    contacts.update(session, rr.duplicate_of, upd, actor=actor, region=region)
                    updated += 1
                    continue
            try:
                contacts.create(session, rec, actor=actor, region=region, allow_duplicate=(duplicate_policy == "import_anyway"))
                created += 1
            except DuplicateContact:
                skipped += 1
    audit.record(session, "contacts.import", actor=actor, data={"created": created, "updated": updated, "skipped": skipped, "invalid": invalid})
    return {"created": created, "updated": updated, "skipped": skipped, "invalid": invalid, "total": pv.total_rows}


EXPORT_COLUMNS = (
    "id", "business_name", "contact_person", "phone_e164", "email", "city", "district", "state", "country", "source_url",
    "source_verification", "lead_source", "lead_stage", "campaign_id", "last_contact_at", "next_followup_at", "notes",
    "tags", "consent_status", "opted_out", "opt_out_reason", "created_at", "updated_at",
)


def _export_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        v = ", ".join(str(x) for x in v)
    if isinstance(v, datetime):
        v = v.isoformat()
    s = str(v)
    if s[:1] in ("=", "+", "-", "@"):  # formula injection guard
        s = "'" + s
    return s


def export_csv(rows: list[Contact]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(EXPORT_COLUMNS)
    for c in rows:
        w.writerow([_export_value(getattr(c, col)) for col in EXPORT_COLUMNS])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def export_xlsx(rows: list[Contact]) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "contacts"
    ws.append(list(EXPORT_COLUMNS))
    for c in rows:
        ws.append([_export_value(getattr(c, col)) for col in EXPORT_COLUMNS])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
