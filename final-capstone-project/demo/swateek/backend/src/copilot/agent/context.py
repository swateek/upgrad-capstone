"""Per-query run context shared by the planner, the executor subagent and the critic gate.

One query = one RunContext, held in a ContextVar for the duration of the run. It carries the
Track B budgets, the source-reference registry and an event log.

Budgets (definitions stated in the report):
  step  = one model call by any role (planner, executor, critic); Track B cap: 10 per query
  tool  = one tool execution; separate cap (default 10)
  token = prompt + completion tokens summed over every model call in the query
It also carries the source-reference registry (the model cites
short refs like [P3]; code maps them to doc_id:rule_id), and an event log for streaming and
tracing. Subagents run inside the same context, so their steps count against the same budget.
"""

from __future__ import annotations

import contextvars
import time
from dataclasses import dataclass, field
from typing import Any

_CURRENT: contextvars.ContextVar[RunContext | None] = contextvars.ContextVar(
    "run_ctx", default=None
)


class BudgetExceeded(RuntimeError):
    def __init__(self, kind: str, used: int, limit: int) -> None:
        super().__init__(f"{kind} budget exceeded ({used}/{limit})")
        self.kind, self.used, self.limit = kind, used, limit


@dataclass
class RunContext:
    step_limit: int
    tool_limit: int
    token_limit: int
    steps: int = 0
    tokens: int = 0
    tool_calls: int = 0
    refs: dict[str, dict[str, Any]] = field(default_factory=dict)  # "P3" -> hit
    tool_payloads: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    session: dict[str, Any] = field(default_factory=dict)  # memory carried across turns
    refusal_hits: list[Any] = field(default_factory=list)  # matched before planning
    critic: list[dict[str, Any]] = field(default_factory=list)  # verdict per review
    drafts: list[str] = field(default_factory=list)  # every reviewed draft, in order
    question: str = ""
    revisions: int = 0
    stopped: str | None = None  # why the run ended early, if it did
    on_event: Any = None  # optional callback(event) for live streaming
    started: float = field(default_factory=time.perf_counter)

    # --- budgets ---------------------------------------------------------------------------
    def take_step(self) -> None:
        """Account one model call; raise once the step budget is spent."""
        if self.steps >= self.step_limit:
            self.stopped = self.stopped or f"step limit ({self.step_limit}) reached"
            raise BudgetExceeded("step", self.steps, self.step_limit)
        self.steps += 1

    def take_tool_call(self) -> None:
        if self.tool_calls >= self.tool_limit:
            self.stopped = self.stopped or f"tool-call limit ({self.tool_limit}) reached"
            raise BudgetExceeded("tool", self.tool_calls, self.tool_limit)
        self.tool_calls += 1

    def add_tokens(self, n: int) -> None:
        self.tokens += n
        if self.tokens > self.token_limit:
            self.stopped = self.stopped or f"token limit ({self.token_limit}) reached"

    @property
    def over_tokens(self) -> bool:
        return self.tokens > self.token_limit

    # --- references --------------------------------------------------------------------------
    def register(self, hit: dict[str, Any]) -> str:
        for ref, h in self.refs.items():
            if h["chunk_id"] == hit["chunk_id"]:
                return ref
        ref = f"P{len(self.refs) + 1}"
        self.refs[ref] = hit
        return ref

    # --- events ------------------------------------------------------------------------------
    def emit(self, kind: str, **data: Any) -> None:
        event = {"type": kind, "t": round(time.perf_counter() - self.started, 2), **data}
        self.events.append(event)
        if self.on_event is not None:
            self.on_event(event)


def current() -> RunContext | None:
    return _CURRENT.get()


def require() -> RunContext:
    ctx = _CURRENT.get()
    if ctx is None:
        raise RuntimeError("no RunContext active; call the harness, not the agent directly")
    return ctx


def activate(ctx: RunContext) -> contextvars.Token:
    return _CURRENT.set(ctx)


def deactivate(token: contextvars.Token) -> None:
    _CURRENT.reset(token)
