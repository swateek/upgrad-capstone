"""FastAPI app: direct tool routes (demo floor), grounded /answer, and the agent /chat.

    uv run uvicorn copilot.api.app:app --reload --port 3401

Nothing here can award, order, debar or approve. Every tool result is returned as a draft.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from copilot.agent.harness import Harness
from copilot.answer import Answerer
from copilot.config import get_settings
from copilot.domains.loader import load_domain
from copilot.retrieval.dense import StaleIndex
from copilot.tools.registry import Toolbox

log = logging.getLogger("copilot.api")
STATE: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    domain = load_domain(settings.domain_dir)
    toolbox = Toolbox(settings, domain)
    STATE.update(settings=settings, domain=domain, toolbox=toolbox, index_error=None)
    try:
        _ = toolbox.retriever  # fail fast on a missing or stale index, but keep serving tools
    except (StaleIndex, OSError, RuntimeError) as err:
        STATE["index_error"] = str(err)
        log.error("retrieval unavailable: %s", err)
    prompt_path = domain.prompts.get("answer")
    STATE["answerer"] = (
        Answerer(settings, domain.path(prompt_path).read_text(encoding="utf-8"))
        if prompt_path
        else None
    )
    STATE["harness"] = None if STATE["index_error"] else Harness(settings, domain, toolbox)
    # one agent run at a time per process: the course endpoint allows 1 active request per key
    STATE["agent_lock"] = threading.Lock()
    yield
    if not STATE["index_error"]:
        toolbox.retriever.dense.client.close()
    STATE.clear()


app = FastAPI(title="Track B copilot", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _client_ip(request: Request) -> str:
    # The web proxy forwards the browser's address. Trusted because the API is only published
    # on 127.0.0.1 and reached through that proxy; do not expose it publicly as-is.
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _limited(key: str, limit: int) -> JSONResponse | None:
    try:
        count, retry_after = toolbox().store.hit(key, 60)
    except Exception:  # noqa: BLE001 - a limiter outage must not take the API down
        return None
    if count <= limit:
        return None
    return JSONResponse(
        {
            "detail": f"Rate limit reached ({limit} per minute). Try again in {retry_after}s.",
            "retry_after": retry_after,
        },
        status_code=429,
        headers={"Retry-After": str(retry_after)},
    )


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Per-client limit on every route except /health (Track B: rate limiting)."""
    if request.url.path != "/health" and STATE.get("toolbox") is not None:
        blocked = _limited(f"rl:ip:{_client_ip(request)}", STATE["settings"].rate_limit_ip_per_min)
        if blocked is not None:
            return blocked
    return await call_next(request)


def toolbox() -> Toolbox:
    return STATE["toolbox"]


@app.get("/health")
def health() -> dict[str, Any]:
    tb = toolbox()
    ok = STATE["index_error"] is None
    return {
        "status": "ok" if ok else "degraded",
        "domain": tb.domain.name,
        "chunker": tb.settings.chunker,
        "index": (
            {"points": tb.retriever.dense.client.count(tb.retriever.dense.collection).count}
            if ok
            else {"error": STATE["index_error"]}
        ),
        "llm_provider": tb.settings.llm_provider,
    }


@app.get("/domain")
def domain_info() -> dict[str, Any]:
    tb = toolbox()
    d = tb.domain
    return {
        "name": d.name,
        "display_name": d.display_name,
        "ui_modes": d.ui_modes,
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "ui_mode": t.ui_mode,
                "input_schema": t.input_model.model_json_schema(),
            }
            for t in tb.tools.values()
        ],
        "instruments": sorted(tb.instruments) if STATE["index_error"] is None else [],
        "draft_notice": "All output is a draft for a human decision-maker. "
        "This system does not award, place orders, or debar.",
    }


@app.get("/listings/{name}")
def listing(name: str) -> Any:
    data = toolbox().listing(name)
    if data is None:
        raise HTTPException(404, f"no listing '{name}' in this domain")
    return data


@app.post("/tools/{name}")
def call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    tb = toolbox()
    spec = tb.tools.get(name)
    if spec is None:
        raise HTTPException(404, f"no tool '{name}' in this domain")
    if spec.is_search and STATE["index_error"]:
        raise HTTPException(503, f"retrieval unavailable: {STATE['index_error']}")
    return {"tool": name, "is_draft": True, "result": spec.call(args)}


class AnswerRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    instrument: str | None = None


@app.post("/answer")
def answer(req: AnswerRequest) -> dict[str, Any]:
    tb = toolbox()
    if STATE["index_error"]:
        raise HTTPException(503, f"retrieval unavailable: {STATE['index_error']}")
    if STATE["answerer"] is None:
        raise HTTPException(501, "this domain has no answer prompt")
    found = tb.search_docs(req.question, req.instrument)
    if "error" in found:
        raise HTTPException(422, found["error"])
    result = STATE["answerer"].answer(req.question, found["hits"])
    return {"question": req.question, "is_draft": True, "hits": found["hits"], **result}


class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=2000)


FINAL_KEYS = (
    "answer",
    "citations",
    "sources",
    "todos",
    "critic",
    "critic_passed",
    "revisions",
    "refusal_rules",
    "steps",
    "tool_calls",
    "tokens",
    "stopped",
    "error",
    "complete",
    "partial",
    "latency_s",
    "session",
    "is_draft",
)


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@app.post("/chat", response_model=None)
async def chat(req: ChatRequest) -> StreamingResponse | JSONResponse:
    """One agent turn as server-sent events. Progress events (todos, tool calls, critic verdicts)
    stream live; the answer text is sent only in the final event, after the critic has run."""
    harness: Harness | None = STATE.get("harness")
    if harness is None:
        raise HTTPException(503, f"agent unavailable: {STATE.get('index_error')}")
    blocked = _limited(f"rl:thread:{req.thread_id}", STATE["settings"].rate_limit_chat_per_min)
    if blocked is not None:  # per-conversation limit on agent turns
        return blocked
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_event(event: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("progress", event))

    def work() -> None:
        try:
            with STATE["agent_lock"]:
                result = harness.run(req.message, req.thread_id, on_event=on_event)
            payloads = _ui_payloads(result["tool_payloads"])
            final = {k: result[k] for k in FINAL_KEYS} | {"payloads": payloads}
            loop.call_soon_threadsafe(queue.put_nowait, ("final", final))
        except Exception as err:  # noqa: BLE001 - always end the stream with a typed event
            loop.call_soon_threadsafe(queue.put_nowait, ("error", {"error": str(err)[:300]}))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, (None, None))

    async def stream():
        threading.Thread(target=work, daemon=True).start()
        while True:
            kind, data = await queue.get()
            if kind is None:
                break
            yield _sse(kind, data)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _ui_payloads(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The last result of each non-search tool, for rich rendering (score sheet, screening)."""
    latest: dict[str, dict[str, Any]] = {}
    for p in payloads:
        spec = toolbox().tools.get(p["tool"])
        if spec and not spec.is_search:
            latest[p["tool"]] = {"tool": p["tool"], "ui_mode": spec.ui_mode, "result": p["result"]}
    return list(latest.values())


@app.get("/threads/{thread_id}")
def thread(thread_id: str) -> dict[str, Any]:
    harness: Harness | None = STATE.get("harness")
    if harness is None:
        raise HTTPException(503, "agent unavailable")
    return harness.history(thread_id)
