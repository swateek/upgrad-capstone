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

from copilot.agent.context import BudgetExceeded, require
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
        func=run, name=spec.name, description=spec.description, args_schema=spec.input_model
    )


def _summary(spec: ToolSpec, payload: dict[str, Any]) -> str:
    if "error" in payload:
        return f"error: {payload['error']}"
    if spec.is_search:
        return f"{len(payload['hits'])} passages"
    return str(payload.get("statement") or payload.get("draft_notice") or "ok")[:160]


def build_tools(toolbox: Toolbox) -> list[StructuredTool]:
    return [make_tool(spec) for spec in toolbox.tools.values()]
