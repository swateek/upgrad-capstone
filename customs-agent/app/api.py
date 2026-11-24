"""HTTP API for the web app (replaces the Streamlit plan: see CLAUDE.md, decision Day 6).

    uv run uvicorn app.api:app --port 8000            # API (and the built web app, if web/dist exists)
    cd web && npm run dev                             # web app with hot reload, proxies /api to :8000

Endpoints
  GET  /api/live                   liveness (container health check; loads nothing)
  GET  /api/health                 models, search method, tracing backend
  POST /api/ask                    {question, mode?, session_id?} -> answer, card, facts, trace link, cost
                                   (one turn of a conversation; session_id continues it)
  POST /api/edit                   {session_id, field, value} -> a fact changed on the card
  GET  /api/clause/{citation_id}   regulation text for the citation viewer
  GET  /api/checklist/{session_id} declaration checklist (PDF) for the latest answered/escalated turn

State flags: the app sets STATE_RULES=all (15 states) unless the environment says otherwise.

Rate limit: 10 questions per minute per client (mentor plan, Day 8); 429 with Retry-After beyond it.
One request at a time reaches the endpoint anyway (src/llm.py queue).

Hosting (Day 13, deploy/vm/):
  ACCESS_CODE=<code>    every /api/ route except /api/live and /api/access needs the access cookie,
                        set by POST /api/access {code}; the web app asks for the code once
  TRUST_PROXY=1         behind Caddy: the client for the rate limit is the address the proxy
                        appended to X-Forwarded-For (the last entry), not the proxy's own
Card edits are screened here (the agent code is frozen): text goes through the question guard and
the clause sanitiser, numbers must be in range (live red-team finding 2, docs/REDTEAM_LIVE.md).
"""

from __future__ import annotations

import hashlib
import hmac
import math
import os
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.tools.lookup_state_rule import covered_states

ROOT = Path(__file__).resolve().parents[1]
WEB_DIST = ROOT / "web" / "dist"
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "10"))
ACCESS_COOKIE = "dr_access"
OPEN_API = ("/api/live", "/api/access")


def access_code() -> str:
    return os.environ.get("ACCESS_CODE", "").strip()


def access_token(code: str) -> str:
    """The cookie value: derived from the code, so the code itself is never stored in the browser."""
    return hmac.new(
        code.encode(), b"declareright-access-v1", hashlib.sha256
    ).hexdigest()


def client_key(request: Request) -> str:
    """Who to rate-limit. Behind our own proxy (TRUST_PROXY=1) every request comes from the proxy,
    so use the address it appended to X-Forwarded-For: the last entry, which a client cannot forge."""
    if os.environ.get("TRUST_PROXY") == "1":
        xff = request.headers.get("x-forwarded-for", "")
        if xff.strip():
            return xff.split(",")[-1].strip()
    return request.client.host if request.client else "local"


# ------------------------------------------------------------------ card edits (screened here)
NUMBER_RANGES = {
    "age": (0, 120),
    "abv": (0, 100),
    "unit_price_usd": (0, 100_000),
    "value_usd": (0, 100_000),
    "unit_ml": (1, 20_000),
}
MAX_TEXT = 120


def _texts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in _texts(v)]
    return []


def edit_problem(field: str, value: Any) -> str | None:
    """Why a card edit is refused, or None. The guard and the sanitiser see every text value;
    numbers must be finite and in range; a quantity must be positive."""
    from src.safety.guard import check_question, sanitise_clause

    for t in _texts(value):
        if len(t) > MAX_TEXT:
            return f"That value is too long (over {MAX_TEXT} characters)."
        if check_question(t).action != "pass" or not sanitise_clause(t)[0]:
            return "That text can't be used as a fact. Describe the item plainly, for example 'Rioja'."
    key = field.split(".", 1)[-1]
    num = value.get("value") if isinstance(value, dict) else value
    if isinstance(num, bool):
        return None
    if isinstance(num, (int, float)):
        if not math.isfinite(num):
            return "That number isn't valid."
        if key in ("quantity", "trip") and num <= 0:
            return "That needs a number above zero."
        lo, hi = NUMBER_RANGES.get(key, (0, 1_000_000))
        if not lo <= num <= hi:
            return f"That number is out of range ({lo} to {hi:,})."
    return None


class AccessIn(BaseModel):
    code: str = Field(min_length=1, max_length=200)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    mode: Literal["planner", "router"] = "planner"
    session_id: str | None = None


class EditIn(BaseModel):
    session_id: str = Field(min_length=1)
    field: str = Field(
        min_length=1,
        max_length=40,
        description='"age", "trip", "exemption_used_last_30_days", "item1.quantity"',
    )
    value: Any
    mode: Literal["planner", "router"] = "planner"


@dataclass
class Service:
    """What the API needs: built once at startup (models load slowly), replaced by fakes in tests."""

    llm: Any
    search: Any
    tracer: Any
    chunks: list[dict]
    sessions: Any = None  # src.agent.session.Sessions; built on first use
    # the last reply per conversation, for the PDF checklist (in memory: a restart forgets it)
    last: dict[str, dict] = field(default_factory=dict)

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

    def conversations(self):
        if self.sessions is None:
            from src.agent.session import Sessions

            self.sessions = Sessions(self.llm, self.search)  # logs/sessions.sqlite3
        return self.sessions


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
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # the app flags all 15 researched arrival states; official runs keep the SPEC's five
        # (stretch, Day 9). Set at server start, not import, so tests and runs are untouched.
        os.environ.setdefault("STATE_RULES", "all")
        yield

    app = FastAPI(title="DeclareRight API", lifespan=lifespan)
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

    @app.get("/api/live")
    def live() -> dict:
        """Liveness for the container health check: answers without loading any model."""
        return {"ok": True}

    @app.get("/api/health")
    def health() -> dict:
        s = svc()
        return {
            "ok": True,
            "chat_model": getattr(s.llm, "chat_model", None),
            "search": getattr(s.search, "method", None),
            "tracing": type(s.tracer).__name__,
            "rate_limit_per_minute": RATE_LIMIT,
            "state_flags": sorted(covered_states()),
        }

    @app.middleware("http")
    async def require_access(request: Request, call_next):
        code = access_code()
        path = request.url.path
        if code and path.startswith("/api/") and path not in OPEN_API:
            got = request.cookies.get(ACCESS_COOKIE, "")
            if not hmac.compare_digest(got, access_token(code)):
                return JSONResponse(
                    {"detail": "Enter the access code to use DeclareRight."},
                    status_code=401,
                )
        return await call_next(request)

    @app.get("/api/access")
    def access_status(request: Request) -> dict:
        code = access_code()
        got = request.cookies.get(ACCESS_COOKIE, "")
        return {
            "required": bool(code),
            "ok": (not code) or hmac.compare_digest(got, access_token(code)),
        }

    @app.post("/api/access")
    def access_login(body: AccessIn, request: Request):
        if (r := limited(request)) is not None:
            return r
        code = access_code()
        if code and not hmac.compare_digest(body.code.strip(), code):
            return JSONResponse({"detail": "That code isn't right."}, status_code=401)
        resp = JSONResponse({"ok": True})
        if code:
            secure = (
                request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
            )
            resp.set_cookie(
                ACCESS_COOKIE,
                access_token(code),
                max_age=30 * 24 * 3600,
                httponly=True,
                samesite="lax",
                secure=secure,
            )
        return resp

    def limited(request: Request) -> JSONResponse | None:
        client = client_key(request)
        wait = limiter.retry_after(client)
        if wait:
            return JSONResponse(
                {
                    "detail": f"Too many questions: {RATE_LIMIT} per minute. Try again in {wait} s."
                },
                status_code=429,
                headers={"Retry-After": str(wait)},
            )
        return None

    def reply(question: str, session: str, mode: str, turn) -> dict:
        s = svc()
        t0 = time.perf_counter()
        run = turn()
        seconds = round(time.perf_counter() - t0, 1)
        try:
            ref = s.tracer.record(
                question, run, mode=mode, session_id=session, seconds=seconds
            )
            trace = {"id": ref.trace_id, "url": ref.url}
        except Exception as e:  # noqa: BLE001 - a tracing failure must not lose the answer
            trace = {"id": None, "url": None, "error": type(e).__name__}
        card = dict(run.card)
        for c in card.get("citations") or []:
            c["label"] = pretty_citation(c["id"], title_of(c["id"]))
        st = s.conversations().state(session)
        out = {
            "session_id": session,
            "outcome": run.answer.outcome if run.answer else "escalated",
            "reason": run.reason,
            "answer": run.answer.model_dump(mode="json") if run.answer else None,
            "card": card,
            "facts": {
                "profile": st.get("profile") or {},
                "basket": st.get("basket") or [],
            },
            "assumptions": run.assumptions,
            "trace": trace,
            "cost": {
                "tool_steps": run.tool_steps,
                "model_calls": run.usage.calls,
                "tokens": run.usage.tokens,
                "seconds": seconds,
            },
            "error": bool(run.error),
        }
        s.last[session] = out
        return out

    @app.post("/api/ask")
    def ask(body: AskIn, request: Request):
        if (r := limited(request)) is not None:
            return r
        session = body.session_id or uuid.uuid4().hex
        convo = svc().conversations()
        return reply(
            body.question,
            session,
            body.mode,
            lambda: convo.turn(session, message=body.question, mode=body.mode),
        )

    @app.post("/api/edit")
    def edit(body: EditIn, request: Request):
        """A fact changed on the answer card: one turn, no model reading, only dependent steps re-run."""
        if (r := limited(request)) is not None:
            return r
        if problem := edit_problem(body.field, body.value):
            raise HTTPException(422, problem)
        convo = svc().conversations()
        if not convo.state(body.session_id).get("basket"):
            raise HTTPException(
                404, "No conversation with that id: ask a question first."
            )
        change = {"field": body.field, "value": body.value}
        return reply(
            f"(changed {body.field} to {body.value})",
            body.session_id,
            body.mode,
            lambda: convo.turn(body.session_id, edit=change, mode=body.mode),
        )

    @app.get("/api/checklist/{session_id}")
    def checklist(session_id: str) -> Response:
        """The declaration checklist for the conversation's latest answer, as a PDF."""
        from app.checklist import CHECKLIST_OUTCOMES, build_pdf

        resp = svc().last.get(session_id)
        if resp is None:
            raise HTTPException(
                404, "No answer for that conversation yet: ask a question first."
            )
        if resp["outcome"] not in CHECKLIST_OUTCOMES:
            raise HTTPException(
                409,
                "Answer the open question first: there is nothing settled to declare yet.",
            )
        return Response(
            build_pdf(resp),
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="declaration-checklist.pdf"'
            },
        )

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

        root = WEB_DIST.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            # resolve first, then require the file to be inside web/dist: "../" (plain or
            # %2e%2e / %2f encoded) must never reach .env, the data or the code (Day 13 red-team)
            f = (root / path).resolve()
            if path and f.is_relative_to(root) and f.is_file():
                return FileResponse(f)
            return FileResponse(root / "index.html")

    return app


app = create_app()
