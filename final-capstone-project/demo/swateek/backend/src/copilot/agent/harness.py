"""The Deep Agents harness: planner -> executor -> critic, built for an 8K-window 8B model.

Built from LangChain's create_agent with Deep Agents' SubAgentMiddleware and LangChain's
TodoListMiddleware (the trimmed configuration measured in Phase 0: ~470 prompt tokens on the
planner's first call instead of ~2,900 for create_deep_agent defaults). No filesystem tools and
no general-purpose subagent: exactly three roles.

  planner   main agent: write_todos, then delegates via the task tool; relays the result
  executor  subagent with the core search tool and the domain pack's tools
  critic    enforced in code on every final answer (CriticGate), deterministic + LLM review

State: LangGraph SQLite checkpointer for the conversation, plus a small session store
(active vendor, active case, last tool) carried into the planner's prompt each turn.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

import yaml
from deepagents import SubAgentMiddleware
from deepagents.backends import StateBackend
from langchain.agents import create_agent
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver

from copilot.agent.context import BudgetExceeded, RunContext, activate, deactivate
from copilot.agent.critic import Critic
from copilot.agent.middleware import BudgetMiddleware, CriticGate, PlannerContext, ToolArgGuard
from copilot.agent.refusals import RefusalPolicy
from copilot.agent.tools import build_tools
from copilot.config import Settings
from copilot.domains.loader import DomainConfig
from copilot.llm import get_provider
from copilot.observability.tracing import Tracer
from copilot.tools.registry import Toolbox

REF = re.compile(r"\[(P\d+)\]")
STOPPED = re.compile(r"^\[stopped: .*\]$")


class SessionStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS sessions (thread_id TEXT PRIMARY KEY, data TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS turns (thread_id TEXT, n INTEGER, data TEXT, "
            "PRIMARY KEY (thread_id, n))"
        )

    def add_turn(self, thread_id: str, turn: dict[str, Any]) -> None:
        n = self.db.execute(
            "SELECT COALESCE(MAX(n), 0) + 1 FROM turns WHERE thread_id = ?", (thread_id,)
        ).fetchone()[0]
        self.db.execute("INSERT INTO turns VALUES (?, ?, ?)", (thread_id, n, json.dumps(turn)))
        self.db.commit()

    def turns(self, thread_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT data FROM turns WHERE thread_id = ? ORDER BY n", (thread_id,)
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def get(self, thread_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT data FROM sessions WHERE thread_id = ?", (thread_id,)
        ).fetchone()
        return json.loads(row[0]) if row else {}

    def put(self, thread_id: str, data: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO sessions (thread_id, data) VALUES (?, ?) "
            "ON CONFLICT(thread_id) DO UPDATE SET data = excluded.data",
            (thread_id, json.dumps(data)),
        )
        self.db.commit()


class Harness:
    def __init__(
        self, settings: Settings, domain: DomainConfig, toolbox: Toolbox, llm: Any = None
    ) -> None:
        self.settings = settings
        self.domain = domain
        self.toolbox = toolbox
        provider = get_provider(settings)
        self.provider_url = f"{provider.base_url}/chat/completions"
        self.llm = llm or ChatOpenAI(
            model=provider.model,
            base_url=provider.base_url,
            api_key=provider.api_key,
            temperature=0,
            max_tokens=settings.agent_max_tokens,
            max_retries=0,  # the Track B retry policy runs in BudgetMiddleware
            timeout=settings.request_timeout_s,
            extra_body=provider.extra_body,
            stream_usage=True,
        )
        p = domain.path
        self.prompts = {
            k: p(v).read_text(encoding="utf-8")
            for k, v in domain.prompts.items()
            if v.endswith(".md")
        }
        self.short = yaml.safe_load(p(domain.prompts["harness"]).read_text(encoding="utf-8"))
        self.policy = RefusalPolicy(domain)
        self.critic = Critic(domain, self.policy, self.llm, self.prompts["critic"])
        self.critic.mode_of_tool = {
            name: ("__search__" if spec.is_search else (spec.ui_mode or ""))
            for name, spec in toolbox.tools.items()
        }
        self.tools = build_tools(toolbox)
        state_dir = settings.data_dir / "state" / domain.name
        state_dir.mkdir(parents=True, exist_ok=True)
        self.sessions = SessionStore(state_dir / "sessions.sqlite")
        self.checkpointer = SqliteSaver(
            sqlite3.connect(state_dir / "threads.sqlite", check_same_thread=False)
        )
        self.agent = self._build()
        self.tracer = Tracer(settings)
        self.provider_name = provider.name

    def _budget(self, role: str) -> BudgetMiddleware:
        return BudgetMiddleware(
            role, self.settings, self.settings.agent_max_tokens, self.provider_url
        )

    def _build(self):
        executor = {
            "name": "executor",
            "description": self.short["executor_description"],
            "system_prompt": self.prompts["executor"],
            "tools": self.tools,
            "model": self.llm,
            "middleware": [self._budget("executor"), ToolArgGuard()],
        }
        return create_agent(
            self.llm,
            tools=[],
            system_prompt=self.prompts["planner"],
            middleware=[
                # CriticGate first: its before_model releases a reviewed executor answer without
                # spending a step; BudgetMiddleware then accounts every real model call.
                CriticGate(
                    self.critic.review,
                    max_revisions=self.settings.agent_max_revisions,
                    search_tools=frozenset(n for n, t in self.toolbox.tools.items() if t.is_search),
                    tool_names=frozenset(self.toolbox.tools),
                ),
                PlannerContext(),
                self._budget("planner"),
                TodoListMiddleware(
                    system_prompt=self.short["todo_system"],
                    tool_description=self.short["todo_tool"],
                ),
                SubAgentMiddleware(
                    backend=StateBackend(),
                    subagents=[executor],
                    system_prompt="",
                    task_description=self.short["task_tool"],
                ),
            ],
            checkpointer=self.checkpointer,
            name="planner",
        )

    def run(
        self, question: str, thread_id: str, on_event: Any = None, tags: list[str] | None = None
    ) -> dict[str, Any]:
        ctx = RunContext(
            step_limit=self.settings.agent_step_limit,
            tool_limit=self.settings.agent_tool_limit,
            token_limit=self.settings.agent_token_limit,
            on_event=on_event,
        )
        ctx.session = self.sessions.get(thread_id)
        ctx.question = question
        ctx.refusal_hits = self.policy.check(question)
        for hit in ctx.refusal_hits:
            ctx.emit("refusal_rule", rule=hit.rule_id, matched=hit.matched)
        token = activate(ctx)
        t0 = time.perf_counter()
        error = None
        state: dict[str, Any] = {}
        trace_ctx = self.tracer.run(
            f"{self.domain.name}-agent",
            thread_id,
            question,
            tags=[self.domain.name, self.provider_name, *(tags or [])],
            metadata={"chunker": self.settings.chunker, "model": self.settings.chat_model},
        )
        trace = trace_ctx.__enter__()
        ctx.callbacks = trace.callbacks
        try:
            state = self.agent.invoke(
                {"messages": [HumanMessage(content=question)]},
                config={
                    "configurable": {"thread_id": thread_id},
                    "recursion_limit": 100,
                    "callbacks": trace.callbacks,
                },
            )
        except BudgetExceeded as err:
            ctx.stopped = ctx.stopped or str(err)
        except Exception as err:  # noqa: BLE001 - surface failures as a typed result
            error = f"{type(err).__name__}: {err}"
            ctx.emit("error", error=error[:300])
        finally:
            deactivate(token)
        draft = _final_text(state.get("messages", []))
        partial = False
        if not draft and ctx.drafts:  # stopped early: release the latest reviewed draft
            draft, partial = ctx.drafts[-1], True
        resolved, citations, unknown = _resolve(draft, ctx.refs)
        self._update_session(thread_id, ctx)
        final_critic = ctx.critic[-1] if ctx.critic else None
        trace.finish(
            output={"answer": resolved, "citations": citations},
            metadata={
                "steps": ctx.steps,
                "tool_calls": ctx.tool_calls,
                "tokens": ctx.tokens,
                "critic_passed": bool(final_critic and final_critic["passed"]),
                "revisions": ctx.revisions,
                "stopped": ctx.stopped,
                "partial": partial,
                "refusal_rules": [h.rule_id for h in ctx.refusal_hits],
            },
        )
        trace_ctx.__exit__(None, None, None)
        self.tracer.flush()
        self.sessions.add_turn(
            thread_id,
            {
                "question": question,
                "answer": resolved,
                "citations": citations,
                "critic_passed": bool(final_critic and final_critic["passed"]),
                "partial": partial,
                "stopped": ctx.stopped,
            },
        )
        return {
            "question": question,
            "thread_id": thread_id,
            "answer": resolved,
            "raw_answer": draft,
            "citations": citations,
            "unknown_refs": unknown,
            "sources": [
                {"ref": r, **{k: v for k, v in h.items() if k != "text"}}
                for r, h in ctx.refs.items()
            ],
            "todos": _this_turn_todos(state.get("messages", []), question),
            "critic": ctx.critic,
            "critic_passed": bool(final_critic and final_critic["passed"]),
            "revisions": ctx.revisions,
            "refusal_rules": [h.rule_id for h in ctx.refusal_hits],
            "steps": ctx.steps,
            "tool_calls": ctx.tool_calls,
            "tokens": ctx.tokens,
            "stopped": ctx.stopped,
            "error": error,
            "complete": error is None and ctx.stopped is None and bool(draft) and not partial,
            "partial": partial,
            "latency_s": round(time.perf_counter() - t0, 2),
            "tool_payloads": ctx.tool_payloads,
            "events": ctx.events,
            "session": self.sessions.get(thread_id),
            "trace_url": trace.url,
            "is_draft": True,
        }

    def history(self, thread_id: str) -> dict[str, Any]:
        """Released turns of a thread: question, resolved answer, citations, critic outcome."""
        return {
            "thread_id": thread_id,
            "turns": self.sessions.turns(thread_id),
            "session": self.sessions.get(thread_id),
        }

    def _update_session(self, thread_id: str, ctx: RunContext) -> None:
        session = dict(ctx.session)
        for p in ctx.tool_payloads:
            spec = self.toolbox.tools.get(p["tool"])
            if spec and spec.state:
                session.update(spec.state(p["args"], p["result"]))
            session["last_tool"] = {
                "tool": p["tool"],
                "args": p["args"],
                "ok": "error" not in p["result"],
            }
        self.sessions.put(thread_id, session)


def _this_turn_todos(messages: list[Any], question: str) -> list[dict[str, Any]]:
    """Todos written during this turn only (the checkpointed state keeps earlier turns')."""
    start = max(
        (
            i
            for i, m in enumerate(messages)
            if isinstance(m, HumanMessage) and m.content == question
        ),
        default=0,
    )
    todos: list[dict[str, Any]] = []
    for m in messages[start:]:
        for call in getattr(m, "tool_calls", None) or []:
            if call.get("name") == "write_todos":
                todos = list(call.get("args", {}).get("todos", []))
    return todos


def _final_text(messages: list[Any]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and not m.tool_calls:
            text = m.content if isinstance(m.content, str) else str(m.content)
            return "" if STOPPED.match(text.strip()) else text.strip()
    return ""


def _resolve(draft: str, refs: dict[str, dict[str, Any]]) -> tuple[str, list[str], list[str]]:
    citations: list[str] = []
    unknown: list[str] = []

    def repl(m: re.Match[str]) -> str:
        ref = m.group(1)
        hit = refs.get(ref)
        if hit is None:
            unknown.append(ref)
            return ""
        if hit["citation"] not in citations:
            citations.append(hit["citation"])
        return f"[{hit['citation']}]"

    return REF.sub(repl, draft).strip(), citations, unknown
