"""Expose the Toolbox to the agent as LangChain tools.

- Search results are labelled with short refs ([P1], [P2], ...) registered in the RunContext.
  The model sees refs, titles and text, never citation ids; code maps refs back at the end.
- Domain tools return a compact, model-facing view (the domain's `compact` hook); the full
  payload is kept in the RunContext for the UI and the critic.
- Every tool call is accounted against the tool budget and logged as events. Tools never raise.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from copilot.agent.context import BudgetExceeded, require
from copilot.cache import normalize_query
from copilot.retrieval.hybrid import rrf
from copilot.tools.registry import Toolbox, ToolSpec

HEADER = re.compile(r"^\[[^\]]+\]\n?")
MAX_HIT_CHARS = 1800  # ~450 tokens per hit keeps five hits inside the retrieved-context budget


def _search_view(payload: dict[str, Any]) -> dict[str, Any]:
    ctx = require()
    if "error" in payload:
        return payload
    out = []
    for h in payload["hits"]:
        ref = ctx.register(
            {
                "chunk_id": f"{h['citation']}#{h['part']}",
                "citation": h["citation"],
                "title": h["title"],
                "instrument": h["instrument"],
                "edition_date": h["edition_date"],
                "synthetic": h["synthetic"],
                "text": h["text"],
            }
        )
        body = HEADER.sub("", h["text"], count=1)
        out.append(
            {
                "ref": ref,
                "title": h["title"],
                "instrument": h["instrument"],
                "edition": h["edition_date"],
                "synthetic": h["synthetic"],
                "text": body[:MAX_HIT_CHARS] + ("…" if len(body) > MAX_HIT_CHARS else ""),
            }
        )
    return {
        "query": payload["query"],
        "results": out,
        "how_to_cite": "Cite with the ref in square brackets, e.g. [P1].",
    }


def _anchor(spec: ToolSpec, kwargs: dict[str, Any], payload: dict[str, Any], question: str):
    """Query anchoring (small-model-log #27): the 8B executor rewrites the user's question into
    its own search query and loses recall that the raw question has. Also search with the
    user's question and fuse both reranked lists (RRF), keeping the usual top-k."""
    if not question or normalize_query(question) == normalize_query(kwargs.get("query", "")):
        return payload
    other = spec.call({**kwargs, "query": question[:500]})
    if "error" in other:
        return payload
    k = len(payload["hits"]) or len(other["hits"])
    fused = rrf(
        {
            "model_query": [h["citation"] + f"#{h['part']}" for h in payload["hits"]],
            "user_question": [h["citation"] + f"#{h['part']}" for h in other["hits"]],
        }
    )
    by_key = {h["citation"] + f"#{h['part']}": h for h in [*payload["hits"], *other["hits"]]}
    return {
        **payload,
        "anchored_on": question[:200],
        "hits": [by_key[key] for key, _, _ in fused[:k]],
    }


class AgentSearchInput(BaseModel):
    """The agent-facing search takes only a query. In the first full e2e run the 8B executor set
    the optional instrument filter on most searches, often to the wrong instrument or an
    invalid name, which hid the right document (small-model-log #30). People can still filter
    through the API and the UI."""

    query: str = Field(min_length=3, max_length=500, description="What to look up in the rules")


def make_tool(spec: ToolSpec) -> StructuredTool:
    def run(**kwargs: Any) -> str:
        ctx = require()
        try:
            ctx.take_tool_call()
        except BudgetExceeded as err:
            ctx.emit("tool_refused", tool=spec.name, reason=str(err))
            return json.dumps({"error": str(err), "retryable": False})
        ctx.emit("tool_call", tool=spec.name, args=kwargs)
        payload = spec.call(kwargs)
        if spec.is_search and "error" not in payload:
            payload = _anchor(spec, kwargs, payload, ctx.question)
        ctx.tool_payloads.append({"tool": spec.name, "args": kwargs, "result": payload})
        if spec.is_search:
            view = _search_view(payload)
        elif spec.compact and "error" not in payload:
            view = spec.compact(payload)
        else:
            view = payload
        ctx.emit(
            "tool_result",
            tool=spec.name,
            ok="error" not in payload,
            summary=_summary(spec, payload),
        )
        return json.dumps(view, ensure_ascii=False, default=str)

    return StructuredTool.from_function(
        func=run,
        name=spec.name,
        description=spec.description,
        args_schema=AgentSearchInput if spec.is_search else spec.input_model,
    )


def _summary(spec: ToolSpec, payload: dict[str, Any]) -> str:
    if "error" in payload:
        return f"error: {payload['error']}"
    if spec.is_search:
        return f"{len(payload['hits'])} passages"
    return str(payload.get("statement") or payload.get("draft_notice") or "ok")[:160]


def build_tools(toolbox: Toolbox) -> list[StructuredTool]:
    return [make_tool(spec) for spec in toolbox.tools.values()]
