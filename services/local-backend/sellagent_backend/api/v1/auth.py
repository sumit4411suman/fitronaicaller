from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_local_auth
from sellagent_backend.security.secret_store import write_secret_file
from sellagent_backend.security.tokens import generate_token, hash_token
from sellagent_backend.services import audit

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(require_local_auth)])


@router.get("/whoami")
def whoami(actor: str = Depends(require_local_auth)) -> dict:
    return {"actor": actor, "scope": "local_operator"}


@router.post("/rotate-local-token")
def rotate(request: Request, db: Session = Depends(get_db)) -> dict:
    """Rotate the desktop<->backend token. The new token is written to the protected token file and returned once."""
    token = generate_token()
    request.app.state.local_token_hash = hash_token(token)
    write_secret_file(request.app.state.settings.local_token_path, token)
    audit.record(db, "auth.rotate_local_token", severity="warning")
    return {"token": token}
