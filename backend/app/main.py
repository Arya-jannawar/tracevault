"""TraceVault API entrypoint.

* /api/v1 routers, typed contracts, generated OpenAPI
* correlation/request IDs on every response
* safe content-free error envelopes (410 for blocked content)
* CSRF: cookie-authenticated mutations require X-TraceVault-Session header
* startup: workspace, optional admin bootstrap, optional synthetic seeding
"""
from __future__ import annotations

import secrets
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .db import SessionLocal
from .errors import TraceVaultError

settings = get_settings()

app = FastAPI(
    title="TraceVault API",
    version="0.1.0",
    description=(
        "Provenance-Aware Deletion and Selective Summary Repair for "
        "Privacy-Preserving RAG Systems — research prototype. Guarantees are "
        "limited to registered components and tested pathways."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173",
                   "http://127.0.0.1:8080", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CSRF_HEADER = "x-tracevault-session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.correlation_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


class CsrfMiddleware(BaseHTTPMiddleware):
    """Cookie-authenticated mutations must carry the custom CSRF header."""

    async def dispatch(self, request, call_next):
        if request.method not in SAFE_METHODS:
            has_cookie = request.cookies.get("tv_session") is not None
            if has_cookie and not request.headers.get(CSRF_HEADER):
                return JSONResponse(
                    status_code=403,
                    content={"code": "csrf_missing",
                             "message": "Missing X-TraceVault-Session header."},
                )
        return await call_next(request)


app.add_middleware(CsrfMiddleware)
app.add_middleware(RequestIdMiddleware)


@app.exception_handler(TraceVaultError)
async def tracevault_error_handler(request: Request, exc: TraceVaultError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message,
                 "request_id": getattr(request.state, "correlation_id", None)},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"code": "validation_failed",
                 "message": "Request validation failed.",
                 "details": exc.errors()[:10]},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    # Never leak document content or stack traces to clients.
    return JSONResponse(
        status_code=500,
        content={"code": "internal_error",
                 "message": "Unexpected server error; see server logs.",
                 "request_id": getattr(request.state, "correlation_id", None)},
    )


# ------------------------------------------------------------------ routers
from .routers import (  # noqa: E402
    audit_r,
    auth_r,
    deletions_r,
    documents_r,
    evaluations_r,
    provenance_r,
    rag_r,
    system_r,
)

API = "/api/v1"
for r in (auth_r.router, documents_r.router, rag_r.router, provenance_r.router,
          deletions_r.router, audit_r.router, evaluations_r.router,
          system_r.router):
    app.include_router(r, prefix=API)


@app.on_event("startup")
def startup() -> None:
    from .fence import get_or_create_default_workspace

    db = SessionLocal()
    try:
        ws = get_or_create_default_workspace(db, settings.workspace_name)
        if settings.seed_on_start:
            from .seed import seed_demo_workspace

            result = seed_demo_workspace(db, ws.id)
            print(f"[tracevault] workspace '{ws.name}' seed: {result}", flush=True)
    finally:
        db.close()


@app.get("/")
def root():
    return {"system": "TraceVault", "api": API,
            "academic_title": (
                "Provenance-Aware Deletion and Selective Summary Repair for "
                "Privacy-Preserving Retrieval-Augmented Generation (RAG) Systems"
            ),
            "is_research_prototype": True}
