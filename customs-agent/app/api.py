"""HTTP API for the web app (replaces the Streamlit plan: see CLAUDE.md, decision Day 6).

    uv run uvicorn app.api:app --port 8000            # API (and the built web app, if web/dist exists)
    cd web && npm run dev                             # web app with hot reload, proxies /api to :8000

Endpoints
  GET  /api/health                 models, search method, tracing backend
  POST /api/ask                    {question, mode?, session_id?} -> answer, card, trace link, cost
  GET  /api/clause/{citation_id}   regulation text for the citation viewer

Rate limit: 10 questions per minute per client (mentor plan, Day 8); 429 with Retry-After beyond it.
One request at a time reaches the endpoint anyway (src/llm.py queue).
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
WEB_DIST = ROOT / "web" / "dist"
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "10"))


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    mode: Literal["planner", "router"] = "planner"
    session_id: str | None = None


@dataclass
class Service:
    """What the API needs: built once at startup (models load slowly), replaced by fakes in tests."""

    llm: Any
    search: Any
    tracer: Any
    chunks: list[dict]

    @classmethod
    def from_env(cls) -> Service:
        from src.llm import LLM
        from src.retrieval.corpus import load_chunks
        from src.tools.search_regulations import RegulationSearch
        from src.tracing import Tracer

        llm = LLM.from_env(run_name="app")
        chunks = load_chunks()
        return cls(
            llm,
            RegulationSearch.from_env(llm, chunks=chunks),
            Tracer.from_env(),
            chunks,
        )


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def retry_after(self, key: str, now: float | None = None) -> int:
        """0 if allowed (and counted), else seconds until the next slot."""
        now = time.monotonic() if now is None else now
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] >= 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return max(1, int(60 - (now - q[0])) + 1)
            q.append(now)
            return 0


def pretty_citation(cid: str, title: str | None = None) -> str:
    """ "19cfr148.33" -> "19 CFR 148.33"; guidance pages get their own title ("CBP - Customs Duty
    Information" -> "CBP: Customs Duty Information")."""
    import re

    if m := re.fullmatch(r"(\d+)(cfr|usc)(\d[\w.]*)", cid):
        return f"{m.group(1)} {m.group(2).upper()} {'§ ' if m.group(2) == 'usc' else ''}{m.group(3)}"
    if m := re.fullmatch(r"htsus(\d[\d.]*)", cid):
        return f"HTSUS {m.group(1)}"
    if m := re.fullmatch(r"htsus-gn-(\d+)", cid):
        return f"HTSUS General Note {m.group(1)}"
    if m := re.fullmatch(r"ofac-faq-(\d+)", cid):
        return f"OFAC FAQ {m.group(1)}"
    if title:
        return title.replace(" - ", ": ", 1)
    return cid


def create_app(service: Service | None = None) -> FastAPI:
    app = FastAPI(title="DeclareRight API")
    state: dict[str, Any] = {"service": service}
    limiter = RateLimiter(RATE_LIMIT)

    def svc() -> Service:
        if state["service"] is None:
            state["service"] = Service.from_env()
        return state["service"]

    def title_of(cid: str) -> str | None:
        if "titles" not in state:
            state["titles"] = {}
            for c in svc().chunks:
                state["titles"].setdefault(
                    c["citation_id"], (c.get("metadata") or {}).get("title")
                )
        return state["titles"].get(cid)

    @app.get("/api/health")
    def health() -> dict:
        s = svc()
        return {
            "ok": True,
            "chat_model": getattr(s.llm, "chat_model", None),
            "search": getattr(s.search, "method", None),
            "tracing": type(s.tracer).__name__,
            "rate_limit_per_minute": RATE_LIMIT,
        }

    @app.post("/api/ask")
    def ask(body: AskIn, request: Request):
        from src.agent.pipeline import answer_question

        client = request.client.host if request.client else "local"
        wait = limiter.retry_after(client)
        if wait:
            return JSONResponse(
                {
                    "detail": f"Too many questions: {RATE_LIMIT} per minute. Try again in {wait} s."
                },
                status_code=429,
                headers={"Retry-After": str(wait)},
            )
        s = svc()
        session = body.session_id or uuid.uuid4().hex
        t0 = time.perf_counter()
        run = answer_question(body.question, llm=s.llm, search=s.search, mode=body.mode)
        seconds = round(time.perf_counter() - t0, 1)
        try:
            ref = s.tracer.record(
                body.question, run, mode=body.mode, session_id=session, seconds=seconds
            )
            trace = {"id": ref.trace_id, "url": ref.url}
        except Exception as e:  # noqa: BLE001 - a tracing failure must not lose the answer
            trace = {"id": None, "url": None, "error": type(e).__name__}
        card = dict(run.card)
        for c in card.get("citations") or []:
            c["label"] = pretty_citation(c["id"], title_of(c["id"]))
        return {
            "session_id": session,
            "outcome": run.answer.outcome if run.answer else "escalated",
            "reason": run.reason,
            "answer": run.answer.model_dump(mode="json") if run.answer else None,
            "card": card,
            "trace": trace,
            "cost": {
                "tool_steps": run.tool_steps,
                "model_calls": run.usage.calls,
                "tokens": run.usage.tokens,
                "seconds": seconds,
            },
            "error": bool(run.error),
        }

    @app.get("/api/clause/{citation_id}")
    def clause(citation_id: str) -> dict:
        from src.tools.search_regulations import NOT_CITABLE

        parts = [
            c
            for c in svc().chunks
            if c["citation_id"] == citation_id and c.get("authority") not in NOT_CITABLE
        ]
        if not parts:
            raise HTTPException(404, f"No regulation text for {citation_id}")
        meta = parts[0].get("metadata") or {}
        return {
            "citation_id": citation_id,
            "label": pretty_citation(citation_id, meta.get("title")),
            "title": (meta.get("title") or parts[0].get("heading_path", "")).replace(
                " - ", ": ", 1
            ),
            "authority": parts[0].get("authority"),
            "source_url": meta.get("source_url"),
            "as_of": meta.get("as_of"),
            "sections": [
                {"heading": c.get("heading_path", ""), "text": c["text"]} for c in parts
            ],
        }

    if (
        WEB_DIST.exists()
    ):  # the built web app, served by the same process (one container)
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = WEB_DIST / path
            return FileResponse(f if path and f.is_file() else WEB_DIST / "index.html")

    return app


app = create_app()
