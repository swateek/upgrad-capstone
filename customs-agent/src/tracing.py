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
            gen = next(  # a follow-up turn's reading is logged as "turn_intake"
                (
                    s
                    for s in llm_steps
                    if s["stage"].startswith(step) or s["stage"] == f"turn_{step}"
                ),
                None,
            )
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
                        {
                            "name": x["tool"],
                            "as_type": "tool",
                            # a step reused from the previous turn has no output of its own
                            "output": x.get(
                                "output", {"reused": "output kept from the previous turn"}
                            ),
                        }
                        for x in t.get("tools", [])
                    ],
                }
            )
        else:
            children.append(
                {"name": step, "as_type": AS_TYPE.get(step, "span"), "output": t}
            )
    # a correction's replan decides which tools re-run: show it before them
    rp = next((c for c in children if c["name"] == "replan"), None)
    tools = next((i for i, c in enumerate(children) if c["name"] == "tools"), None)
    if rp is not None and tools is not None and children.index(rp) > tools:
        children.remove(rp)
        children.insert(tools, rp)
    # writer and verifier calls: before the verifier's code check, which runs after them
    at = next(
        (i for i, c in enumerate(children) if c["name"] == "verifier"), len(children)
    )
    children[at:at] = [
        {
            "name": s["stage"],
            "as_type": "generation",
            "output": s.get("content"),
            "raw": s,
        }
        for s in llm_steps
    ]
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


def _ms(node: dict) -> float:
    """A step's recorded duration in ms: model calls carry it in `raw`, search in its output."""
    for src in (node.get("raw"), node.get("metadata"), node.get("output")):
        if isinstance(src, dict) and isinstance(src.get("ms"), (int, float)):
            return float(src["ms"])
    return 0.0


STEP_MS = 1.0  # the least a step takes on the timeline (keeps the order visible)


def _count(nodes: list[dict]) -> int:
    return sum(1 + _count(n.get("children", [])) for n in nodes)


def _set_start(obs: Any, ns: int) -> None:
    """Back-date an observation's start (the SDK has no start-time argument)."""
    # a test double, or an SDK that changed: keep the default start
    try:
        obs._otel_span._start_time = ns
    except AttributeError:
        pass


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

    def lay_out(self, root: Any, children: list[dict], seconds: float | None) -> None:
        """Emit the steps on a timeline. Traces are built after the answer, so without this every
        observation would start and end at the moment of sending (latency 0 in Langfuse). The
        root spans the question's wall time (`seconds`); each step lasts its recorded `ms` (model
        calls, search), one after another; untimed code steps take 1 ms, so that Langfuse, which
        orders steps by start time, shows them in the order they ran."""
        timed = sum(_ms(c) for c in children) + _count(children) * STEP_MS
        total_ms = max(timed, (seconds or 0) * 1000)
        end = time.time_ns()
        cur = end - int(total_ms * 1e6)
        _set_start(root, cur)
        for c in children:
            cur = self._emit(root, c, cur)

    def _emit(self, parent: Any, node: dict, at: int | None = None) -> int:
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
        start = at if at is not None else time.time_ns()
        _set_start(child, start)
        cur = start
        for c in node.get("children", []):
            cur = self._emit(child, c, cur)
        end = max(cur, start + int(max(_ms(node), STEP_MS) * 1e6))
        child.end(end_time=end)
        return end

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
            self.lay_out(root, data["children"], seconds)
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
