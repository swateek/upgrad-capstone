"""Agent middleware: Track B budgets, retry policy, planner context, and the critic gate.

Attached to every agent (planner and executor subagent):
  BudgetMiddleware   one step per model call (cap 10 per query, shared via RunContext), the
                     per-call 8K window guard (trims old tool output if a prompt would overflow),
                     the per-query token cap, and the 429/503 retry policy around each call.
Planner only:
  PlannerContext     prepends session memory and any matched refusal rule to the system prompt.
  CriticGate         reviews every final answer before it leaves the agent; one revision max.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse, hook_config
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    convert_to_openai_messages,
)
from langchain_core.utils.function_calling import convert_to_openai_tool

from copilot.agent.context import BudgetExceeded, require
from copilot.config import Settings
from copilot.llm.budget import count_message_tokens, get_tokenizer
from copilot.llm.retry import call_with_retry

REF_ANY = re.compile(r"\s?\[P\d+\]")
TRUNCATE_TO = 600  # chars kept from an old tool result when the window is tight


def _override(request: ModelRequest, **changes: Any) -> ModelRequest:
    if hasattr(request, "override"):
        return request.override(**changes)
    return dataclasses.replace(request, **changes)


class BudgetMiddleware(AgentMiddleware):
    def __init__(self, role: str, settings: Settings, max_tokens: int, provider_url: str) -> None:
        super().__init__()
        self.role = role
        self.settings = settings
        self.max_tokens = max_tokens
        self.provider_url = provider_url
        self.tok = get_tokenizer(settings.tokenizer_id)

    @property
    def name(self) -> str:  # one instance per agent; names must be unique per agent
        return f"BudgetMiddleware[{self.role}]"

    @hook_config(can_jump_to=["end"])
    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        ctx = require()
        reason = None
        if ctx.over_tokens:
            reason = ctx.stopped
        else:
            try:
                ctx.take_step()
            except BudgetExceeded:
                reason = ctx.stopped
        if reason:
            ctx.emit("stopped", role=self.role, reason=reason)
            return {"jump_to": "end", "messages": [AIMessage(content=f"[stopped: {reason}]")]}
        ctx.emit("model_call", role=self.role, step=ctx.steps)
        return None

    def _estimate(self, request: ModelRequest) -> int:
        msgs = convert_to_openai_messages(list(request.messages))
        if request.system_message is not None:
            msgs = [{"role": "system", "content": request.system_message.content}, *msgs]
        tools = [
            t if isinstance(t, dict) else convert_to_openai_tool(t) for t in request.tools or []
        ]
        return count_message_tokens(self.tok, msgs, tools)

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        ctx = require()
        limit = self.settings.context_window_tokens - self.max_tokens
        est = self._estimate(request)
        if est > limit:  # trim the oldest tool results first, keep the newest intact
            msgs = list(request.messages)
            tool_idx = [i for i, m in enumerate(msgs) if isinstance(m, ToolMessage)][:-1]
            for i in tool_idx:
                m = msgs[i]
                if isinstance(m.content, str) and len(m.content) > TRUNCATE_TO:
                    msgs[i] = m.model_copy(
                        update={
                            "content": m.content[:TRUNCATE_TO]
                            + " …[truncated to fit the 8K window]"
                        }
                    )
                    request = _override(request, messages=msgs)
                    est = self._estimate(request)
                    if est <= limit:
                        break
            ctx.emit("trimmed", role=self.role, prompt_tokens=est)
        if est > limit:
            raise BudgetExceeded("window", est, limit)
        response = call_with_retry(
            lambda: handler(request),
            provider="llm",
            url=self.provider_url,
            delays=self.settings.retry_delays_s,
        )
        for msg in getattr(response, "result", []) or []:
            usage = getattr(msg, "usage_metadata", None) or {}
            ctx.add_tokens(int(usage.get("total_tokens", 0) or 0))
        return response


class PlannerContext(AgentMiddleware):
    """Adds per-turn context to the planner's system prompt: session memory and refusals."""

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        ctx = require()
        notes = []
        if ctx.session:
            notes.append("Session memory (from earlier turns): " + json.dumps(ctx.session))
        for hit in ctx.refusal_hits:
            notes.append(
                f"This request matches refusal rule {hit.rule_id}. You must decline that part and "
                f'say why, using this wording: "{hit.wording}" You may still explain the rule '
                "that applies, with citations."
            )
        if notes:
            base = request.system_message.content if request.system_message else ""
            request = _override(
                request, system_message=SystemMessage(content=f"{base}\n\n" + "\n".join(notes))
            )
        return handler(request)


class ExecutorContext(AgentMiddleware):
    """Gives the executor the user's own question and the session memory on every call.

    The executor otherwise sees only the planner's task description. After a critic rejection
    the planner re-delegates with the critic's problems, often without the case id or the
    question itself; the 8B executor then guessed an id (it copied the prompt's example
    "case_001", later invented "case_123") and answered the feedback instead of the user
    (small-model-log #38)."""

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        ctx = require()
        notes = []
        if ctx.question:
            notes.append(f"The user's question (answer this, with the tools): {ctx.question}")
        if ctx.session:
            notes.append("Session memory (from earlier turns): " + json.dumps(ctx.session))
        if notes:
            base = request.system_message.content if request.system_message else ""
            request = _override(
                request, system_message=SystemMessage(content=f"{base}\n\n" + "\n".join(notes))
            )
        return handler(request)


class CriticGate(AgentMiddleware):
    """The critic gate on the planner. Two entry points, one rule: nothing leaves unreviewed.

    - Executor answers come back as the `task` tool result. They are reviewed *before* the
      planner's next model call and, if they pass, released verbatim (jump to end). The
      planner never re-types the answer, so refs survive and no step is spent relaying.
    - Answers the planner writes itself (greetings, refusals) are reviewed after the model call.
    A failed review sends the problems back once; after that the latest draft is released with
    its verdict attached. Only deterministic problems block; LLM notes are advisory.
    """

    def __init__(
        self,
        review: Callable[[str, str], dict[str, Any]],
        max_revisions: int = 1,
        search_tools: frozenset[str] = frozenset(),
        tool_names: frozenset[str] = frozenset(),
    ):
        super().__init__()
        self.review = review
        self.max_revisions = max_revisions
        self.search_tools = search_tools
        # the 8B model also "cites" tool names in brackets; those are never sources
        names = "|".join(re.escape(n) for n in sorted(tool_names))
        self.tool_cite = re.compile(rf"\s?\[(?:{names})\]") if names else None

    def _repair(self, draft: str) -> str:
        """Known 8B habit (small-model-log #16): it appends [P1]-style refs to screening and bid
        answers even when nothing was searched. With no search in the run such refs carry no
        meaning, so code removes them and logs the repair. After a search, an unknown ref is a
        grounding failure and is left for the critic to reject."""
        ctx = require()
        if self.tool_cite is not None:
            stripped = self.tool_cite.sub("", draft)
            if stripped != draft:
                ctx.emit("repaired", what="removed tool names written as citations")
                draft = stripped
        if any(p["tool"] in self.search_tools for p in ctx.tool_payloads):
            return draft
        cleaned = REF_ANY.sub("", draft)
        if cleaned != draft:
            ctx.emit("repaired", what="removed refs from an answer with no search results")
            cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned)
        return cleaned.strip()

    def _judge(self, draft: str) -> dict[str, Any] | None:
        """Return None to release the draft, or a state update asking for a revision."""
        ctx = require()
        ctx.drafts.append(draft)
        verdict = self.review(ctx.question, draft)
        ctx.critic.append(verdict)
        ctx.emit(
            "critic",
            passed=verdict["passed"],
            problems=verdict["problems"],
            advisory=verdict.get("llm", []),
            revision=ctx.revisions,
        )
        if verdict["passed"] or ctx.revisions >= self.max_revisions:
            return None
        ctx.revisions += 1
        feedback = (
            "The critic rejected the answer. Delegate again to the executor with these problems "
            "to fix:\n- " + "\n- ".join(verdict["problems"])
        )
        return {"messages": [HumanMessage(content=feedback)]}

    @hook_config(can_jump_to=["end"])
    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        ctx = require()
        last = state["messages"][-1]
        if not isinstance(last, ToolMessage) or last.name != "task" or ctx.stopped:
            return None
        draft = last.content if isinstance(last.content, str) else str(last.content)
        draft = self._repair(draft.strip())
        update = self._judge(draft)
        if update is None:
            return {"jump_to": "end", "messages": [AIMessage(content=draft)]}
        return update

    @hook_config(can_jump_to=["model"])
    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        ctx = require()
        last = state["messages"][-1]
        if not isinstance(last, AIMessage) or last.tool_calls or ctx.stopped:
            return None
        if any(d == str(last.content).strip() for d in ctx.drafts):
            return None  # already reviewed (released relay)
        update = self._judge(str(last.content).strip())
        return None if update is None else {"jump_to": "model", **update}


class ToolArgGuard(AgentMiddleware):
    """Malformed tool arguments (Track B): the validation error goes back to the model and it
    may retry once per tool; a second malformed call for the same tool is refused. Bad calls
    count against the tool budget and are logged, so a confused model cannot loop."""

    MAX_RETRIES = 1

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        ctx = require()
        name = request.tool_call.get("name", "?")
        result = handler(request)
        if not (isinstance(result, ToolMessage) and result.status == "error"):
            return result
        try:
            ctx.take_tool_call()  # validation failures never reach the tool's own accounting
        except BudgetExceeded:
            pass
        ctx.arg_errors[name] = ctx.arg_errors.get(name, 0) + 1
        ctx.emit(
            "tool_arg_error",
            tool=name,
            attempt=ctx.arg_errors[name],
            error=str(result.content)[:200],
        )
        if ctx.arg_errors[name] > self.MAX_RETRIES:
            return ToolMessage(
                content=json.dumps(
                    {
                        "error": f"Arguments for {name} were invalid twice; no more retries. Answer "
                        "with what you have, or say the request could not be completed.",
                        "retryable": False,
                    }
                ),
                tool_call_id=result.tool_call_id,
                name=name,
                status="error",
            )
        return result
