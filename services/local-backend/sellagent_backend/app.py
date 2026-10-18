"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sellagent_ai.conversation import ConversationEngine
from sellagent_ai.llm import make_provider
from sellagent_kb import seed_fitron_defaults
from starlette.exceptions import HTTPException as StarletteHTTPException

from sellagent_backend.api.v1 import (
    ai,
    audio_tests,
    auth,
    calls,
    campaigns,
    contacts,
    devices,
    followups,
    health,
    knowledge,
    reports,
    speech,
    system,
    transcribe,
    ws,
)
from sellagent_backend.api.v1 import settings as settings_api
from sellagent_backend.config import API_PREFIX, APP_NAME, APP_VERSION, Settings, get_settings
from sellagent_backend.db import engine_for, make_session_factory, migrate
from sellagent_backend.lan import LanServer
from sellagent_backend.security.pairing import PairingManager
from sellagent_backend.security.secret_store import read_secret_file, write_secret_file
from sellagent_backend.security.tls import ensure_certificate
from sellagent_backend.security.tokens import generate_token, hash_token
from sellagent_backend.services import settings_service
from sellagent_backend.telecom import AndroidCompanionAdapter, ManualAdapter
from sellagent_backend.ws.hub import Hub

log = logging.getLogger("sellagent")


def _setup_logging(settings: Settings) -> None:
    settings.ensure_dirs()
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        from logging.handlers import RotatingFileHandler

        handlers.append(RotatingFileHandler(settings.logs_dir / "backend.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers, force=True)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def create_device_app(core: FastAPI) -> FastAPI:
    """Restricted app for the LAN listener: shares state with the core app, exposes device routes only."""
    dev = FastAPI(title=f"{APP_NAME} device endpoint", version=APP_VERSION, docs_url=None, redoc_url=None, openapi_url=None)
    dev.state = core.state  # shared
    dev.include_router(health.router, prefix=API_PREFIX, include_in_schema=False)
    dev.include_router(devices.device_public_router, prefix=API_PREFIX)
    dev.include_router(ws.router, prefix=API_PREFIX)

    @dev.middleware("http")
    async def _only_public(request: Request, call_next):  # type: ignore[no-untyped-def]
        allowed = ("/api/v1/health/ping", "/api/v1/devices/pair", "/api/v1/devices/pair/result", "/api/v1/devices/me", "/api/v1/ws/device")
        if not any(request.url.path == a or request.url.path.startswith(a + "/") for a in allowed):
            return JSONResponse({"error": "not available on the LAN interface", "code": "forbidden"}, status_code=403)
        return await call_next(request)

    return dev


def create_app(settings: Settings | None = None, *, local_token: str | None = None) -> FastAPI:
    settings = settings or get_settings()
    _setup_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        engine = engine_for(settings)
        migrate.upgrade(engine)
        sf = make_session_factory(engine)
        with sf() as s:
            n = seed_fitron_defaults(s)
            if n:
                log.info("seeded %d FITRON knowledge entries", n)
            s.commit()
        token = local_token or read_secret_file(settings.local_token_path)
        if not token:
            token = generate_token()
            write_secret_file(settings.local_token_path, token)
        app.state.local_token_hash = hash_token(token)
        from sellagent_backend.security.auth import jwt_secret

        app.state.jwt_secret = jwt_secret(settings.data_dir)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = sf
        app.state.started_at = datetime.now(UTC)
        app.state.pairing = PairingManager(settings.pairing_code_ttl_seconds, settings.pairing_max_attempts)
        app.state.hub = Hub(sf)
        app.state.uploads = {}
        app.state.telecom = {"manual": ManualAdapter(), "android_companion": AndroidCompanionAdapter(app.state.hub, sf)}
        cert, key, fp = ensure_certificate(settings.data_dir)
        app.state.tls_fingerprint = fp
        app.state.lan = LanServer(create_device_app(app), settings.lan_host, settings.lan_port, str(cert), str(key), fp)
        with sf() as s:
            app.state.lan_requested = bool(settings.lan_enabled or settings_service.get(s, "network.lan_pairing_enabled"))

        def conversation_engine(use_llm: bool = True) -> ConversationEngine:
            with sf() as s2:
                kind, model = settings_service.get(s2, "ai.llm_provider"), settings_service.get(s2, "ai.llm_model")
            return ConversationEngine(make_provider(kind, ollama_url=settings.ollama_base_url, llamacpp_url=settings.llamacpp_base_url), model=model, use_llm=use_llm and kind != "none")

        app.state.conversation_engine = conversation_engine

        async def housekeeping() -> None:
            while True:
                try:
                    if app.state.lan_requested and not app.state.lan.running:
                        await app.state.lan.start()
                    elif not app.state.lan_requested and app.state.lan.running:
                        await app.state.lan.stop()
                except Exception:  # noqa: BLE001
                    log.exception("housekeeping failed")
                await asyncio.sleep(5)

        from sellagent_backend.workers import WorkerManager

        app.state.workers = WorkerManager(sf, app.state.hub, settings.reports_dir)
        app.state.hub.on_emergency_stop.append(lambda: (app.state.workers.ai.cancel_all(), app.state.workers.speech.cancel_all()))
        from sellagent_backend.autonomy import AutonomyManager, default_components

        app.state.autonomy = AutonomyManager(sf, conversation_engine, app.state.workers.emit, default_components(settings))
        app.state.autonomy.loop = asyncio.get_running_loop()
        app.state.hub.on_emergency_stop.append(app.state.autonomy.emergency_stop)
        if not getattr(settings, "disable_workers", False):
            app.state.workers.start()
        task = asyncio.create_task(housekeeping())
        log.info("%s %s backend ready on http://%s:%s (data: %s)", APP_NAME, APP_VERSION, settings.host, settings.port, settings.data_dir)
        try:
            yield
        finally:
            task.cancel()
            app.state.autonomy.stop("backend shutting down")
            await app.state.workers.stop()
            if app.state.lan.running:
                await app.state.lan.stop()
            engine.dispose()

    app = FastAPI(title=f"{APP_NAME} local backend", version=APP_VERSION, lifespan=lifespan, docs_url="/docs", openapi_url="/openapi.json", description="Local, privacy-first backend for the SELL AGENT desktop app. Binds to localhost; LAN listener is opt-in and device-only.")

    @app.middleware("http")
    async def _request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail: Any = exc.detail
        body = detail if isinstance(detail, dict) and "code" in detail else {"code": "http_error", "error": str(detail)}
        body["request_id"] = getattr(request.state, "request_id", None)
        return JSONResponse(body, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"code": "validation_error", "error": "request validation failed", "detail": exc.errors(), "request_id": getattr(request.state, "request_id", None)}, status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error (request %s)", getattr(request.state, "request_id", None))
        return JSONResponse({"code": "internal_error", "error": "internal error; see backend log", "request_id": getattr(request.state, "request_id", None)}, status_code=500)

    for r in (health.router, auth.public_router, auth.router, auth.users_router, calls.safety_router, contacts.router, contacts.sup_router, campaigns.router, calls.router, calls.calls_router, followups.router, knowledge.router, ai.router, speech.router, reports.router, reports.audit_router, settings_api.router, settings_api.backup_router, devices.router, devices.device_public_router, audio_tests.router, system.router, reports.generated_router, ws.router, transcribe.router):
        app.include_router(r, prefix=API_PREFIX)
    return app
