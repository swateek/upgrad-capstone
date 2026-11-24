"""Per-turn run context: budgets (plan §4.6) and the event log the trace and the card carry.

Caps per question turn: model calls (settings.agent_step_limit, listwise rerank calls count),
tool calls (agent_tool_limit) and tokens (agent_token_limit, prompt + completion). The context is
active for one graph invocation (a contextvar, as in the reference app), so nodes reach it
without putting non-serialisable objects into the checkpointed state.
"""

from __future__ import annotations

import contextvars
import time
from dataclasses import dataclass, field
from typing import Any

from customs.config import Settings


class BudgetExceeded(RuntimeError):
    def __init__(self, what: str, used: int, limit: int) -> None:
        super().__init__(f"{what} budget exceeded: {used} > {limit}")
        self.what = what


@dataclass
class RunContext:
    settings: Settings
    mode: str
    model_calls: int = 0
    tool_calls: int = 0
    tokens: int = 0
    embed_requests: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)
    # this turn's objects (never checkpointed)
    case: Any = None  # the calculator Case
    assessment: Any = None
    results: list[dict[str, Any]] = field(default_factory=list)
    sources: list[Any] = field(default_factory=list)

    # --- accounting ---------------------------------------------------------------------------
    def before_model_call(self) -> None:
        if self.model_calls + 1 > self.settings.agent_step_limit:
            raise BudgetExceeded("model call", self.model_calls + 1, self.settings.agent_step_limit)

    def after_model_call(self, node: str, result: Any) -> None:
        """result: a ChatResult (JSON retries inside one logical call count as calls)."""
        calls = getattr(result, "calls", 1) or 1
        tokens = getattr(result, "total_tokens", 0) or 0
        self.model_calls += calls
        self.tokens += tokens
        self.event("model_call", node=node, calls=calls, tokens=tokens,
                   seconds=getattr(result, "seconds", None))  # fmt: skip
        if self.tokens > self.settings.agent_token_limit:
            raise BudgetExceeded("token", self.tokens, self.settings.agent_token_limit)
        if self.model_calls > self.settings.agent_step_limit:
            raise BudgetExceeded("model call", self.model_calls, self.settings.agent_step_limit)

    def tool_call(self, name: str, result: dict) -> None:
        self.tool_calls += 1
        self.event("tool_call", tool=name, error=result.get("error"))
        if self.tool_calls > self.settings.agent_tool_limit:
            raise BudgetExceeded("tool call", self.tool_calls, self.settings.agent_tool_limit)

    def event(self, kind: str, **data: Any) -> None:
        self.events.append({"event": kind, **data})

    def stats(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "tokens": self.tokens,
            "embed_requests": self.embed_requests,
            "seconds": round(time.perf_counter() - self.started, 3),
        }


_current: contextvars.ContextVar[RunContext | None] = contextvars.ContextVar(
    "customs_run_context", default=None
)


def activate(ctx: RunContext) -> contextvars.Token:
    return _current.set(ctx)


def deactivate(token: contextvars.Token) -> None:
    _current.reset(token)


def current() -> RunContext:
    ctx = _current.get()
    if ctx is None:
        raise RuntimeError("no active run context")
    return ctx
