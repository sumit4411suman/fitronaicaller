"""Local AI: provider status, model inventory, model download (explicit opt-in), chat test, benchmark trigger,
conversation simulation (labelled simulation, never a real call)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sellagent_ai.conversation import ConversationContext, ConversationStateMachine, KnowledgeFact, State
from sellagent_ai.guardrails import check_reply
from sellagent_ai.language import detect
from sellagent_ai.llm import ChatMessage, ProviderUnavailable, collect, make_provider
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_area
from sellagent_backend.api.schemas import ChatTestIn, ConversationStepIn, ModelPullIn
from sellagent_backend.api.v1.errors import bad_request
from sellagent_backend.db.models import AIRun
from sellagent_backend.services import settings_service

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(require_area("ai"))])

_sim_sessions: dict[str, tuple[ConversationStateMachine, ConversationContext, object]] = {}


def _provider(request: Request, db: Session):
    s = request.app.state.settings
    kind = settings_service.get(db, "ai.llm_provider")
    return make_provider(kind, ollama_url=s.ollama_base_url, llamacpp_url=s.llamacpp_base_url), settings_service.get(db, "ai.llm_model")


@router.get("/status")
def status(request: Request, db: Session = Depends(get_db)) -> dict:
    provider, model = _provider(request, db)
    ok, msg = provider.available()
    models: list[dict] = []
    if ok:
        try:
            models = provider.list_models()
        except ProviderUnavailable as exc:
            msg = str(exc)
    installed = any(m.get("name", "").split(":")[0] == model.split(":")[0] and (":" not in model or m.get("name") == model) for m in models)
    return {"provider": provider.name, "available": ok, "message": msg, "configured_model": model, "configured_model_installed": installed, "models": models, "external_network_allowed": bool(request.app.state.settings.allow_external_network) or bool(settings_service.get(db, "privacy.allow_external_network")), "offline_capable": ok and installed}


@router.get("/catalog")
def catalog() -> dict:
    """Candidate models for a 16 GB CPU-only PC. Sizes are approximate download sizes; verify in Ollama before pulling."""
    return {"note": "Nothing is downloaded automatically. Benchmarks on YOUR hardware decide the pick (python -m sellagent_ai.benchmark).", "candidates": [
        {"name": "qwen3:1.7b", "params": "1.7B", "approx_download_gb": 1.4, "approx_ram_gb": 2.5, "license": "Apache-2.0", "notes": "Default candidate. Hindi/English capable; set think=false for latency."},
        {"name": "qwen2.5:3b", "params": "3B", "approx_download_gb": 1.9, "approx_ram_gb": 3.5, "license": "Qwen Research License (NON-COMMERCIAL)", "license_warning": "Qwen2.5-3B is released under a research licence that does not allow commercial use. Selling FITRON is commercial: get written permission from Alibaba Cloud or choose qwen3:1.7b / qwen3:4b (Apache-2.0).", "notes": "Blueprint alternative. Pull requires acknowledging the licence."},
        {"name": "qwen3:4b", "params": "4B", "approx_download_gb": 2.6, "approx_ram_gb": 5, "license": "Apache-2.0", "notes": "3B-class alternative; slower first token on CPU. (Qwen2.5-3B was dropped: Qwen Research License is non-commercial.)"},
    ]}


@router.post("/models/pull")
async def pull_model(body: ModelPullIn, request: Request, db: Session = Depends(get_db)) -> dict:
    allow = bool(request.app.state.settings.allow_external_network) or bool(settings_service.get(db, "privacy.allow_external_network"))
    if not body.acknowledge_download:
        raise bad_request("acknowledge_download must be true: this downloads a model (size shown in /ai/catalog)")
    if body.model.startswith("qwen2.5") and not body.acknowledge_license:
        raise bad_request("qwen2.5 models use the non-commercial Qwen Research License; set acknowledge_license=true after confirming you have permission", code="license_ack_required")
    provider, _ = _provider(request, db)
    if provider.name != "ollama":
        raise bad_request("model pull is only supported through Ollama; for llama.cpp place the GGUF file manually (models/README.md)")
    try:
        last: dict = {}
        def _run() -> dict:
            nonlocal last
            for ev in provider.pull(body.model, allow_network=allow):  # type: ignore[attr-defined]
                last = ev
            return last
        last = await asyncio.to_thread(_run)
    except PermissionError as exc:
        raise bad_request(str(exc), code="network_disabled") from exc
    except Exception as exc:  # noqa: BLE001
        raise bad_request(f"pull failed: {exc}", code="pull_failed") from exc
    return {"model": body.model, "status": last.get("status"), "done": last.get("status") == "success"}


@router.post("/chat-test")
async def chat_test(body: ChatTestIn, request: Request, db: Session = Depends(get_db)) -> dict:
    provider, model = _provider(request, db)
    lang = body.language if body.language != "auto" else ("hi" if detect(body.prompt) in ("hi", "mixed") else "en")
    sys_prompt = "Reply briefly in Hindi (Devanagari)." if lang == "hi" else "Reply briefly in English."
    try:
        res = await asyncio.to_thread(collect, provider, [ChatMessage("system", sys_prompt), ChatMessage("user", body.prompt)], model=model, max_tokens=body.max_tokens, timeout=request.app.state.settings.llm_timeout_seconds)
    except ProviderUnavailable as exc:
        db.add(AIRun(kind="llm", provider=provider.name, model=model, success=False, error=str(exc), prompt_chars=len(body.prompt)))
        raise bad_request(str(exc), code="provider_unavailable") from exc
    gr = check_reply(res.text, approved_facts=[{"price_inr": 1999}], state="diagnostic")
    db.add(AIRun(kind="llm", provider=provider.name, model=model, prompt_chars=len(body.prompt), output_chars=len(res.text), first_token_ms=res.first_token_ms, total_ms=res.total_ms, tokens_per_second=res.tokens_per_second, success=True, guardrail_result=gr.to_dict()))
    return {"text": res.text, "detected_language": detect(res.text), "first_token_ms": res.first_token_ms, "total_ms": res.total_ms, "tokens_per_second": res.tokens_per_second, "guardrail": gr.to_dict(), "label": "diagnostic (not a call)"}


@router.post("/simulate/{session_id}")
def simulate(session_id: str, body: ConversationStepIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """SIMULATION ONLY: exercise the conversation engine with typed text. No phone, no audio, no contact record."""
    from sellagent_kb.service import approved_facts

    if session_id == "new" or session_id not in _sim_sessions:
        import uuid

        session_id = uuid.uuid4().hex
        from sellagent_ai.persona import ConversationMemory

        _sim_sessions[session_id] = (ConversationStateMachine(State.CONNECTED), ConversationContext(authorized=True), ConversationMemory())
    sm, ctx, memory = _sim_sessions[session_id]
    if sm.is_terminal:
        raise bad_request("simulation finished; start a new one", code="terminal")
    engine = request.app.state.conversation_engine(use_llm=body.use_llm)
    facts = [KnowledgeFact(f"kb:{d.id}#v{d.version}", d.title, d.category, d.body, d.structured) for d in approved_facts(db)]
    from sellagent_backend.services import persona_service

    persona = persona_service.load_persona(db)
    if body.utterance:
        memory.observe("prospect", body.utterance)  # type: ignore[attr-defined]
    turn = engine.respond(sm, body.utterance, facts=facts, ctx=ctx, preferred_language=persona_service.effective_language(db, body.language, persona), contact_person="Demo Owner", business_name="Demo Gym", persona=persona, memory=memory if persona else None)  # type: ignore[arg-type]
    memory.observe("agent", turn.agent_text)  # type: ignore[attr-defined]
    return {"session_id": session_id, "label": "SIMULATION", "persona": persona.name if persona else None, "cues": turn.cues, "memory": memory.summary(), "state": sm.state.value, "agent_text": turn.agent_text, "language": turn.language, "knowledge_refs": turn.knowledge_refs, "source": turn.source, "guardrail": turn.guardrail.to_dict() if turn.guardrail else None, "terminal": sm.is_terminal, "outcome": turn.outcome, "llm": turn.llm_metrics}


@router.get("/runs")
def runs(db: Session = Depends(get_db), limit: int = 100) -> list[dict]:
    from sqlalchemy import select

    rows = db.scalars(select(AIRun).order_by(AIRun.created_at.desc()).limit(min(limit, 1000)))
    return [{"id": r.id, "created_at": r.created_at, "kind": r.kind, "provider": r.provider, "model": r.model, "first_token_ms": r.first_token_ms, "total_ms": r.total_ms, "tokens_per_second": r.tokens_per_second, "rss_mb": r.rss_mb, "success": r.success, "error": r.error, "offline": r.offline} for r in rows]


@router.post("/chat-stream")
async def chat_stream(body: ChatTestIn, request: Request) -> StreamingResponse:
    """Streams the local model's reply as Server-Sent Events (data: {"token": ...}), through the AI worker so only
    one CPU inference runs at a time. The final event carries metrics and the guardrail verdict."""
    import asyncio
    import json
    import time

    with request.app.state.session_factory() as db:
        provider, model = _provider(request, db)
    lang = body.language if body.language != "auto" else ("hi" if detect(body.prompt) in ("hi", "mixed") else "en")
    sys_prompt = "Reply briefly in Hindi (Devanagari)." if lang == "hi" else "Reply briefly in English."
    msgs = [ChatMessage("system", sys_prompt), ChatMessage("user", body.prompt)]
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    timeout = request.app.state.settings.llm_timeout_seconds

    def _produce(cancel, push) -> None:  # type: ignore[no-untyped-def]
        for piece in provider.stream(msgs, model=model, max_tokens=body.max_tokens, cancel=cancel, timeout=timeout):
            push(piece)

    job = request.app.state.workers.ai.submit_stream("chat_stream", _produce, loop, queue)

    async def gen():  # type: ignore[no-untyped-def]
        t0 = time.perf_counter()
        first = None
        parts: list[str] = []
        yield f"event: start\ndata: {json.dumps({'job_id': job.id, 'model': model, 'provider': provider.name})}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    job.cancel.cancel()
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout)
                except TimeoutError:
                    job.cancel.cancel()
                    yield f"event: error\ndata: {json.dumps({'error': 'timeout'})}\n\n"
                    break
                if item is None:
                    break
                if isinstance(item, dict):
                    yield f"event: error\ndata: {json.dumps(item)}\n\n"
                    continue
                if first is None:
                    first = time.perf_counter()
                parts.append(item)
                yield f"data: {json.dumps({'token': item}, ensure_ascii=False)}\n\n"
        finally:
            text = "".join(parts)
            total = (time.perf_counter() - t0) * 1000
            gr = check_reply(text, approved_facts=[{"price_inr": 1999}], state="diagnostic") if text else None
            done = {"job_id": job.id, "status": job.status, "first_token_ms": ((first - t0) * 1000) if first else None, "total_ms": total, "chars": len(text), "guardrail": gr.to_dict() if gr else None, "label": "diagnostic (not a call)"}
            with request.app.state.session_factory() as db2:
                db2.add(AIRun(kind="llm", provider=provider.name, model=model, prompt_chars=len(body.prompt), output_chars=len(text), first_token_ms=done["first_token_ms"], total_ms=total, success=job.status == "done", error=job.error))
                db2.commit()
            yield f"event: done\ndata: {json.dumps(done, default=str)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
