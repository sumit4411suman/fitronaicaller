from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_local_auth
from sellagent_backend.api.schemas import KnowledgeApprove, KnowledgeIn, KnowledgeOut, KnowledgeReject, KnowledgeSupersede, Ok, RetrieveOut
from sellagent_backend.api.v1.errors import bad_request, not_found
from sellagent_backend.db.models import KnowledgeDocument
from sellagent_kb import KnowledgeError, approve, create_document, reject, retrieve, screen_for_injection, supersede
from sellagent_kb import service as kbs

router = APIRouter(prefix="/knowledge", tags=["knowledge"], dependencies=[Depends(require_local_auth)])


@router.get("", response_model=list[KnowledgeOut])
def list_docs(db: Session = Depends(get_db), status: str | None = None, category: str | None = None) -> list[KnowledgeDocument]:
    q = select(KnowledgeDocument).order_by(KnowledgeDocument.category, KnowledgeDocument.title, KnowledgeDocument.version.desc())
    if status:
        q = q.where(KnowledgeDocument.status == status)
    if category:
        q = q.where(KnowledgeDocument.category == category)
    return list(db.scalars(q))


@router.get("/categories")
def categories() -> dict:
    return {"categories": list(kbs.CATEGORIES)}


@router.post("", response_model=KnowledgeOut, status_code=201)
def create(body: KnowledgeIn, db: Session = Depends(get_db)) -> KnowledgeDocument:
    try:
        return create_document(db, **body.model_dump())
    except KnowledgeError as exc:
        raise bad_request(str(exc)) from exc


@router.post("/import", response_model=KnowledgeOut, status_code=201)
async def import_doc(db: Session = Depends(get_db), file: UploadFile = File(...), category: str = "general", language: str = "en") -> KnowledgeDocument:
    """Import a .txt/.md document as UNTRUSTED, pending review. Injection screening flags are attached."""
    data = await file.read()
    if len(data) > 2_000_000:
        raise bad_request("file too large (2 MB max)")
    name = (file.filename or "upload.txt").lower()
    if not name.endswith((".txt", ".md", ".csv")):
        raise bad_request("only .txt, .md and .csv imports are supported in this version; convert PDF/DOCX to text first")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    try:
        return create_document(db, title=file.filename or "Imported document", body=text, category=category, language=language, source=f"import:{file.filename}", trusted=False)
    except KnowledgeError as exc:
        raise bad_request(str(exc)) from exc


@router.get("/retrieve", response_model=list[RetrieveOut])
def do_retrieve(q: str = Query(min_length=1, max_length=500), db: Session = Depends(get_db), limit: int = Query(5, ge=1, le=20), category: str | None = None, include_unapproved: bool = False) -> list[RetrieveOut]:
    return [RetrieveOut(ref=r.ref, document_id=r.document_id, title=r.title, category=r.category, text=r.text, score=r.score, structured=r.structured) for r in retrieve(db, q, limit=limit, category=category, include_unapproved=include_unapproved)]


@router.post("/screen")
def screen(body: dict) -> dict:
    return {"flags": screen_for_injection(str(body.get("text", "")))}


@router.get("/{doc_id}", response_model=KnowledgeOut)
def get_doc(doc_id: str, db: Session = Depends(get_db)) -> KnowledgeDocument:
    d = db.get(KnowledgeDocument, doc_id)
    if d is None:
        raise not_found("document not found")
    return d


@router.post("/{doc_id}/approve", response_model=KnowledgeOut)
def approve_doc(doc_id: str, body: KnowledgeApprove, db: Session = Depends(get_db)) -> KnowledgeDocument:
    try:
        d = approve(db, doc_id, actor="operator", acknowledge_flags=body.acknowledge_flags)
        kbs._finalize_supersede(db, d)
        return d
    except KnowledgeError as exc:
        raise (not_found if "not found" in str(exc) else bad_request)(str(exc)) from exc


@router.post("/{doc_id}/reject", response_model=KnowledgeOut)
def reject_doc(doc_id: str, body: KnowledgeReject, db: Session = Depends(get_db)) -> KnowledgeDocument:
    try:
        return reject(db, doc_id, actor="operator", reason=body.reason)
    except KnowledgeError as exc:
        raise not_found(str(exc)) from exc


@router.post("/{doc_id}/supersede", response_model=KnowledgeOut, status_code=201)
def supersede_doc(doc_id: str, body: KnowledgeSupersede, db: Session = Depends(get_db)) -> KnowledgeDocument:
    try:
        return supersede(db, doc_id, body=body.body, actor="operator", title=body.title, structured=body.structured, expires_at=body.expires_at)
    except KnowledgeError as exc:
        raise not_found(str(exc)) from exc


@router.delete("/{doc_id}", response_model=Ok)
def delete_doc(doc_id: str, db: Session = Depends(get_db)) -> Ok:
    try:
        kbs.delete(db, doc_id, actor="operator")
    except KnowledgeError as exc:
        raise not_found(str(exc)) from exc
    return Ok()
