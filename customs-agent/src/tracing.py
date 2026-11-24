"""Traces: one per question, one child observation per pipeline step (rubric: trace dashboard).

Langfuse when LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_HOST are set; otherwise one JSON
line per question in logs/trace.jsonl (CLAUDE.md stack: Langfuse, fallback trace.jsonl). Everything
is PII-masked first (src/safety/pii.py). Traces are built from the AgentRun after the answer, so the
agent code has no tracing calls in it; each step's duration is kept in its metadata (`ms`).

    tracer = Tracer.from_env()
    ref = tracer.record(question, run, mode="planner", session_id="...", seconds=9.4)
    ref.trace_id, ref.url        # url is None for the file fallback
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.safety.pii import mask

ROOT = Path(__file__).resolve().parents[1]
TRACE_FILE = ROOT / "logs" / "trace.jsonl"

AS_TYPE = {  # pipeline step -> Langfuse observation type
    "guard": "guardrail",
    "intake": "generation",
    "planner": "generation",
    "executor": "chain",
    "search_regulations": "retriever",
    "verifier": "evaluator",
    "budget": "guardrail",
}


@dataclass(frozen=True)
class TraceRef:
    trace_id: str
    url: str | None = None


def spans(question: str, run: Any, mode: str) -> dict:
    """The trace as plain data: root input/output and ordered child steps (masked)."""
    answer = json.loads(run.answer.model_dump_json()) if run.answer else None
    llm_steps = list(run.usage.steps)
    children: list[dict] = []
    for t in run.trace:
        step = t.get("step", "step")
        if step in ("intake", "planner"):
            gen = next((s for s in llm_steps if s["stage"].startswith(step)), None)
            if gen:
                llm_steps.remove(gen)
            children.append(
                {
                    "name": step,
                    "as_type": "generation",
                    "output": t.get("output") or t.get("plan") or t,
                    "metadata": {k: v for k, v in t.items() if k not in ("output",)},
                    "raw": gen,
                }
            )
        elif step == "executor":
            children.append(
                {
                    "name": "tools",
                    "as_type": "chain",
                    "output": {"plan": t.get("plan"), "outcome": t.get("outcome")},
                    "children": [
                        {"name": x["tool"], "as_type": "tool", "output": x["output"]}
                        for x in t.get("tools", [])
                    ],
                }
            )
        else:
            children.append(
                {"name": step, "as_type": AS_TYPE.get(step, "span"), "output": t}
            )
    for s in llm_steps:  # writer and verifier calls
        children.append(
            {
                "name": s["stage"],
                "as_type": "generation",
                "output": s.get("content"),
                "raw": s,
            }
        )
    return mask(
        {
            "name": "declare-right",
            "input": {"question": question, "mode": mode},
            "output": answer,
            "metadata": {
                "outcome": answer["outcome"] if answer else None,
                "reason": run.reason,
                "error": run.error,
                "tool_steps": run.tool_steps,
                "model_calls": run.usage.calls,
                "tokens": run.usage.tokens,
                "plan_fallback": run.plan_fallback,
                "retrieved_ids": run.retrieved_ids,
            },
            "children": children,
        }
    )


class FileTracer:
    def __init__(self, path: Path = TRACE_FILE) -> None:
        self.path = path

    def record(
        self,
        question: str,
        run: Any,
        *,
        mode: str,
        session_id: str | None = None,
        seconds: float | None = None,
    ) -> TraceRef:
        tid = uuid.uuid4().hex
        data = {
            "trace_id": tid,
            "session_id": session_id,
            "seconds": seconds,
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            **spans(question, run, mode),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
        return TraceRef(tid, None)


class LangfuseTracer:
    def __init__(self) -> None:
        from langfuse import Langfuse

        self.host = os.environ["LANGFUSE_HOST"].rstrip("/")
        self.client = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=self.host,
            mask=lambda *, data, **_: mask(data),
        )
        self._project = os.environ.get("LANGFUSE_PROJECT_ID")

    def _url(self, trace_id: str) -> str | None:
        if self._project:
            return f"{self.host}/project/{self._project}/traces/{trace_id}"
        try:
            return self.client.get_trace_url(trace_id=trace_id)
        except Exception:  # noqa: BLE001 - server unreachable: the trace still exports later
            return None

    def _emit(self, parent: Any, node: dict) -> None:
        raw = node.get("raw") or {}
        kw: dict[str, Any] = {
            "name": node["name"],
            "as_type": node["as_type"],
            "output": node.get("output"),
        }
        meta = dict(node.get("metadata") or {})
        if raw:
            meta.update({"ms": raw.get("ms"), "attempt": raw.get("attempt")})
            if node["as_type"] == "generation":
                kw["usage_details"] = {"total": int(raw.get("tokens") or 0)}
                kw["model"] = os.environ.get("CHAT_MODEL") or os.environ.get(
                    "LLM_MODEL"
                )
        if meta:
            kw["metadata"] = meta
        child = parent.start_observation(**kw)
        for c in node.get("children", []):
            self._emit(child, c)
        child.end()

    def record(
        self,
        question: str,
        run: Any,
        *,
        mode: str,
        session_id: str | None = None,
        seconds: float | None = None,
    ) -> TraceRef:
        from langfuse import propagate_attributes

        data = spans(question, run, mode)
        with propagate_attributes(
            session_id=session_id, trace_name=data["name"], tags=[mode]
        ), self.client.start_as_current_observation(
            name=data["name"],
            as_type="agent",
            input=data["input"],
            metadata={**data["metadata"], "seconds": seconds},
        ) as root:
            for c in data["children"]:
                self._emit(root, c)
            root.update(output=data["output"])
            tid = root.trace_id
        return TraceRef(tid, self._url(tid))

    def flush(self) -> None:
        self.client.flush()


class Tracer:
    @staticmethod
    def from_env():
        keys = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
        if all(os.environ.get(k) for k in keys):
            try:
                return LangfuseTracer()
            except ImportError:
                pass
        return FileTracer()
