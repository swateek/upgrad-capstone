"""FastAPI app (plan §9, §13).

    uv run uvicorn customs.api.app:app --port 3501      # single worker

Routes (the web proxy forwards only these):
    GET  /health                    offline: config, agent freeze version, store
    POST /chat                      {message, thread_id?} -> text/event-stream:
                                    queued? started node* (card | error)
    GET  /threads/{id}              facts, history and the last card of a live conversation
    POST /threads/{id}/facts        {profile: {...}, lines: {"1": {...}}} -> the same stream,
                                    asked as a correction ("Correction to my facts: ...")

Run as a single worker: the one-request gate to the course endpoint is per process (plan
§4.6). Starting the app and /health send nothing to upgrad; a question does.
Questions are never logged; traces go through the PII mask.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from customs import __version__
from customs.api.service import THREAD_ID, AgentService, RateLimited, correction_message
from customs.config import get_settings
from customs.llm.endpoints import EndpointNotConfigured, validate

settings = get_settings()
app = FastAPI(title="US Customs Assistant", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)
app.state.service = None


def service() -> AgentService:
    if app.state.service is None:
        app.state.service = AgentService(settings)
    return app.state.service


def client_of(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = Field(default=None, pattern=THREAD_ID.pattern)


class FactsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: dict[str, Any] = Field(default_factory=dict)
    lines: dict[int, dict[str, Any]] = Field(default_factory=dict)


PROFILE_FIELDS = {"age", "trip_hours", "arrived_directly_from", "exemption_used_last_30_days",
                  "arrival_state"}  # fmt: skip
LINE_FIELDS = {"quantity", "container_ml", "abv", "value_usd", "origin"}


def sse(events: Iterator[dict]) -> StreamingResponse:
    def body() -> Iterator[str]:
        for ev in events:
            yield f"event: {ev['event']}\ndata: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(body(), media_type="text/event-stream",
                             headers={"cache-control": "no-cache", "x-accel-buffering": "no"})  # fmt: skip


def stream_question(thread_id: str, message: str, request: Request) -> StreamingResponse:
    svc = service()
    try:
        svc.check_limits(thread_id, client_of(request))
    except RateLimited as err:
        raise HTTPException(status_code=429, detail=err.what) from None
    return sse(svc.ask(thread_id, message, client_of(request)))


@app.get("/health")
def health() -> dict:
    try:
        validate(settings)  # keys and certificates present; offline
        endpoints = "configured"
    except EndpointNotConfigured as err:
        endpoints = f"not configured: {err}"
    svc = app.state.service
    return {
        "status": "ok",
        "version": __version__,
        "agent": svc.version if svc else None,
        "mode": settings.agent_mode,
        "endpoints": endpoints,
        "tracing": bool(settings.langfuse_public_key and settings.langfuse_secret_key),
        "answer_cache": settings.answer_cache_enabled,
    }


@app.post("/chat")
def chat(body: ChatIn, request: Request) -> StreamingResponse:
    thread_id = body.thread_id or service().new_thread_id()
    return stream_question(thread_id, body.message.strip(), request)


@app.get("/threads/{thread_id}")
def get_thread(thread_id: str) -> JSONResponse:
    if not THREAD_ID.match(thread_id):
        raise HTTPException(status_code=404, detail="not found")
    t = service().thread(thread_id)
    if t is None:
        raise HTTPException(status_code=404, detail="This conversation has expired.")
    return JSONResponse(t)


@app.post("/threads/{thread_id}/facts")
def edit_facts(thread_id: str, body: FactsIn, request: Request) -> StreamingResponse:
    if not THREAD_ID.match(thread_id):
        raise HTTPException(status_code=404, detail="not found")
    t = service().thread(thread_id)
    if t is None or not t.get("facts"):
        raise HTTPException(status_code=404, detail="This conversation has expired.")
    bad = set(body.profile) - PROFILE_FIELDS
    bad |= {k for e in body.lines.values() for k in e} - LINE_FIELDS
    if bad:
        raise HTTPException(status_code=422, detail=f"not editable: {sorted(bad)}")
    if not body.profile and not any(body.lines.values()):
        raise HTTPException(status_code=422, detail="nothing to change")
    msg = correction_message(body.profile, body.lines, t["facts"].get("basket", []))
    return stream_question(thread_id, msg, request)
