"""The customs agent: one LangGraph StateGraph (plan §4.1).

    guard -> intake -> prepare (normalise + scope) -> clarify -> plan -> execute -> audit
          -> write -> verify -> END
    guard -> rag -> END                                   (single_rag mode)

- guard: injection / evasion / declaration requests refused in code, before any model call.
- intake: strict-JSON facts; on a reply or correction it updates the current facts (delta).
- prepare: units and restrictions in code; whole-question scope notes end the turn.
- clarify: answer-changing facts missing -> ONE question (SPEC §6); after the one exchange a
  still-missing age / trip / 30-day fact escalates.
- plan: planner (strict JSON) -> validate_plan -> the planner once more with the errors -> the
  code router's plan (`plan_fallback`). `router` mode uses the router only. After an answer, a
  correction reuses the previous plan when it is still valid (only stale steps change).
- execute: the code executor (or the model, `tool_calling` mode); then caps, flags, citations.
- audit: plan-level failures -> plan once more -> escalate. Calculator escalations end here.
- write / verify: handles only; wording failures -> the writer once more -> escalate; the model
  review is advisory.

Caps per turn (model calls, tool calls, tokens) raise BudgetExceeded, which escalates. State is
checkpointed per thread (SQLite); per-turn objects (the Case, sources) live in the RunContext.
"""

from __future__ import annotations

import functools
import operator
import sqlite3
from collections.abc import Callable
from typing import Annotated, Any, TypedDict

import openai
from langgraph.graph import END, START, StateGraph

from customs.agent import card as cards
from customs.agent.context import BudgetExceeded, RunContext, activate, current, deactivate
from customs.agent.executor import audit, cite, execute, finalise
from customs.agent.guard import get_guard
from customs.agent.intake import (
    delta,
    dump,
    ground,
    merge_reply_lines,
    run_intake,
    stale_steps,
)
from customs.agent.planner import (
    Plan,
    plan_json,
    repair,
    router_plan,
    run_planner,
    validate_plan,
)
from customs.agent.rag import run_rag
from customs.agent.tool_calling import execute_tool_calling
from customs.agent.verifier import advisory_review, check_wording
from customs.agent.writer import WriterOut, run_writer
from customs.config import Settings, get_settings
from customs.llm.budget import TokenBudgetExceeded
from customs.llm.chat import ChatClient, MalformedOutput
from customs.observability.tracing import Tracer
from customs.retrieval.service import RegulationSearch
from customs.tools.calc import Case, new_case, step_normalise, step_restrictions
from customs.tools.facts import AGE, TRIP, USED, clarify_question, missing_facts
from customs.tools.models import Line, Profile
from customs.tools.registry import run_tool
from customs.tools.tables import Tables, load_tables

MODES = ("planner", "router", "tool_calling", "single_rag")
HARD_FACTS = {AGE, TRIP, USED}
BASKET_QUESTION = "What alcohol or tobacco are you bringing back, how much, and what did it cost?"


def prohibited_line(a, sources) -> str:
    s = next((x.handle for x in sources if any(r.startswith(("R4", "R12")) for r in x.rules)),
             sources[0].handle if sources else None)  # fmt: skip
    cite_ = f" [{s}]" if s else ""
    if "possibly_cuban_declare" in a.notes and "cuban_prohibited" not in a.notes:
        return ("No allowance can be given: this brand is also made in Cuba and the origin is "
                f"unclear, so declare it and tell the officer where it was made{cite_}.")  # fmt: skip
    return f"No: Cuban-origin alcohol and tobacco can't be brought in, wherever you bought them{cite_}."


class State(TypedDict, total=False):
    # kept across turns (checkpointed)
    history: Annotated[list[dict], operator.add]
    facts: dict | None
    asked: str | None  # the open clarifying question (one exchange per question)
    asked_fields: list[str]
    plan: list[dict] | None  # the last validated plan
    answered: bool
    # this turn
    message: str
    card: dict | None
    route: str
    stale: list[str]
    plan_errors: list[str]
    plan_source: str
    replans: int
    rewrites: int
    writer_out: dict | None
    problems: list[str]


class CustomsAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        chat: ChatClient | None = None,
        search: RegulationSearch | None = None,
        checkpointer: Any = None,
        tracer: Tracer | None = None,
        tables: Tables | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.tracer = tracer or Tracer(self.settings)
        self.chat = chat or ChatClient(self.settings, tracer=self.tracer)
        self.tables = tables or load_tables()
        self.search = search or RegulationSearch(self.settings, tables=self.tables)
        self.guard = get_guard()
        if checkpointer is None:
            from langgraph.checkpoint.sqlite import SqliteSaver

            d = self.settings.data_dir / "state"
            d.mkdir(parents=True, exist_ok=True)
            checkpointer = SqliteSaver(
                sqlite3.connect(d / "threads.sqlite", check_same_thread=False)
            )
        self.checkpointer = checkpointer
        self.graph = self._build()

    # --- public -----------------------------------------------------------------------------
    def ask(
        self,
        thread_id: str,
        message: str,
        mode: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        mode = mode or self.settings.agent_mode
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}")
        ctx = RunContext(self.settings, mode)
        token = activate(ctx)
        try:
            with self.tracer.run(thread_id, message, [mode, *(tags or [])], metadata) as tr:
                out = self.graph.invoke(
                    {"message": message},
                    config={
                        "configurable": {"thread_id": thread_id},
                        "callbacks": tr.callbacks,
                        "recursion_limit": 40,
                    },
                )
                card = dict(out["card"])
                card["meta"] = {
                    **card.get("meta", {}),
                    **ctx.stats(),
                    "plan": [s["step"] for s in out.get("plan") or []]
                    if card["outcome"] == "answered"
                    else [],
                    "plan_source": out.get("plan_source"),
                    "events": ctx.events,
                    "trace_url": tr.url,
                }
                tr.finish(
                    output={k: card.get(k) for k in ("outcome", "kind", "owe_usd", "bottom_line")},
                    metadata={k: str(v) for k, v in ctx.stats().items()},
                )
                self.tracer.score("outcome", card["outcome"])
            return card
        finally:
            deactivate(token)
            self.tracer.flush()

    def state(self, thread_id: str) -> dict[str, Any]:
        snap = self.graph.get_state({"configurable": {"thread_id": thread_id}})
        return dict(snap.values) if snap else {}

    # --- graph ------------------------------------------------------------------------------
    def _build(self):
        g = StateGraph(State)
        nodes: dict[str, Callable] = {
            "guard": self._guard,
            "rag": self._rag,
            "intake": self._intake,
            "prepare": self._prepare,
            "clarify": self._clarify,
            "plan": self._plan,
            "execute": self._execute,
            "audit": self._audit,
            "write": self._write,
            "verify": self._verify,
        }
        for name, fn in nodes.items():
            g.add_node(name, self._safe(fn))
        g.add_edge(START, "guard")
        targets = {n: n for n in nodes} | {"end": END}
        for name in nodes:
            g.add_conditional_edges(name, lambda s: s.get("route", "end"), targets)
        return g.compile(checkpointer=self.checkpointer)

    def _safe(self, fn: Callable) -> Callable:
        @functools.wraps(fn)
        def node(state: State) -> dict:
            try:
                return fn(state)
            except (BudgetExceeded, TokenBudgetExceeded) as err:
                return self._escalate(state, "budget", str(err))
            except MalformedOutput as err:
                return self._escalate(state, "malformed_output", str(err))
            except (openai.APIStatusError, openai.APIConnectionError) as err:
                return self._escalate(state, "model_unavailable", type(err).__name__)

        return node

    # --- helpers ------------------------------------------------------------------------------
    def _end(self, state: State, card: cards.Card, **extra: Any) -> dict:
        return {
            "route": "end",
            "card": card.model_dump(),
            "history": [
                {"role": "user", "content": state["message"]},
                {"role": "assistant", "content": card.bottom_line},
            ],
            **extra,
        }

    def _escalate(self, state: State, reason: str, detail: str | None = None) -> dict:
        ctx = current()
        case: Case | None = ctx.case
        handoff = None
        if case is not None:
            handoff = run_tool(case, "escalate_to_human", {"reason": reason.replace("_", " ")})
            ctx.event("escalate_to_human", reason=reason)
        a = getattr(ctx, "assessment", None)
        profile = case.profile if case is not None else None
        c = cards.escalated(reason, detail, handoff, a, self.tables, profile)
        return self._end(state, c, asked=None, asked_fields=[])

    def _question(self, state: State) -> str:
        users = [h["content"] for h in state.get("history") or [] if h["role"] == "user"]
        return " ".join([*users, state["message"]])

    def _case(self, state: State) -> Case:
        f = state["facts"]
        case = new_case(
            Profile.model_validate(f["profile"]),
            [Line.model_validate(x) for x in f["basket"]],
            self.tables,
        )
        step_normalise(case)
        step_restrictions(case)
        return case

    # --- nodes --------------------------------------------------------------------------------
    def _guard(self, state: State) -> dict:
        reset = {"card": None, "stale": [], "plan_errors": [], "replans": 0, "rewrites": 0,
                 "writer_out": None, "problems": [], "plan_source": None}  # fmt: skip
        hit = self.guard.check(state["message"])
        if hit:
            current().event("guard", rule=hit.rule)
            return {**reset, **self._end(state, cards.refused(hit.wording, hit.rule))}
        route = "rag" if current().mode == "single_rag" else "intake"
        return {**reset, "route": route}

    def _rag(self, state: State) -> dict:
        c = run_rag(self.chat, self.search, state.get("history") or [], state["message"])
        return self._end(state, c)

    def _intake(self, state: State) -> dict:
        old = state.get("facts")
        f = run_intake(self.chat, state["message"], old, state.get("asked"))
        new, dropped = dump(f, self._question(state))
        if dropped:
            current().event("unsupported_flag_dropped", flags=dropped)
        if old and state.get("asked") and "basket" not in (state.get("asked_fields") or []):
            merged = merge_reply_lines(old, new)
            if merged:
                current().event("reply_line_merged", merged=merged)
        fixes = ground(new, self._question(state), self.tables)
        if fixes:
            current().event("facts_grounded", fixes=fixes)
        changed = delta(old, new)
        stale = stale_steps(changed) if state.get("answered") else []
        if changed:
            current().event("facts_changed", fields=changed, stale=stale)
        return {"facts": new, "stale": stale, "route": "prepare"}

    def _prepare(self, state: State) -> dict:
        case = self._case(state)
        ctx = current()
        ctx.case = case
        if case.scope:
            return self._end(state, cards.out_of_scope([f"scope_note:{case.scope}"], self.tables))
        if not case.basket:
            if state.get("asked"):
                return self._escalate(state, "missing_facts", "no items")
            return self._end(state, cards.clarify(BASKET_QUESTION, ["basket"]),
                             asked=BASKET_QUESTION, asked_fields=["basket"])  # fmt: skip
        held = [nl for nl in case.lines if nl.status in ("prohibited", "possibly_cuban")]
        if not case.admissible and not held:
            notes = [n for n in case.notes if n.startswith("scope_note:")]
            return self._end(state, cards.out_of_scope(notes, self.tables))
        return {"route": "clarify"}

    def _clarify(self, state: State) -> dict:
        case = current().case
        fields = missing_facts(case.profile, case.basket, self.tables)
        if fields and not state.get("asked"):
            q = clarify_question(fields)
            return self._end(state, cards.clarify(q, fields), asked=q, asked_fields=fields)
        if state.get("asked"):
            hard = [f for f in fields if f in HARD_FACTS]
            if hard:
                return self._escalate(state, "missing_facts", ", ".join(hard))
        return {"route": "plan", "asked": None, "asked_fields": []}

    def _plan(self, state: State) -> dict:
        ctx = current()
        case = self._case(state)
        mode = ctx.mode
        errors = state.get("plan_errors") or []
        if mode == "router":
            return {"plan": plan_json(router_plan(case)), "plan_source": "router",
                    "route": "execute"}  # fmt: skip
        prev = state.get("plan")
        if not errors and state.get("answered") and prev:
            p = Plan.model_validate({"steps": prev})
            if not validate_plan(p, case):
                ctx.event("plan_reused", stale=state.get("stale"))
                return {"plan": prev, "plan_source": "reused", "route": "execute"}
        try:
            p = self._repaired(run_planner(self.chat, case, errors=errors or None,
                                           stale=state.get("stale")), case)  # fmt: skip
            errs = validate_plan(p, case)
            if errs:
                ctx.event("plan_invalid", errors=errs, steps=[s.step for s in p.steps])
                p = self._repaired(run_planner(self.chat, case, errors=errs,
                                               stale=state.get("stale")), case)  # fmt: skip
                errs = validate_plan(p, case)
        except MalformedOutput:
            errs = ["planner reply unreadable"]
        if errs:
            ctx.event("plan_fallback", errors=errs)
            return {"plan": plan_json(router_plan(case)), "plan_source": "fallback",
                    "route": "execute"}  # fmt: skip
        return {"plan": plan_json(p), "plan_source": "planner", "route": "execute"}

    def _repaired(self, p: Plan, case: Case) -> Plan:
        p, fixes = repair(p, case)
        if fixes:
            current().event("plan_repaired", fixes=fixes)
        return p

    def _execute(self, state: State) -> dict:
        ctx = current()
        case = self._case(state)
        plan = Plan.model_validate({"steps": state["plan"]})
        if ctx.mode == "tool_calling":
            case, results, stats = execute_tool_calling(
                self.chat, plan, case.profile, case.basket, self.tables
            )
            ctx.event("tool_calling", **stats)
        else:
            results = execute(plan, case)
        ctx.case = case
        ctx.results = results
        ctx.assessment = finalise(case)
        return {"route": "audit"}

    def _audit(self, state: State) -> dict:
        ctx = current()
        case, a = ctx.case, ctx.assessment
        errs = audit(case, ctx.results, a)
        if errs:
            ctx.event("audit_failed", errors=errs)
            if state.get("replans", 0) == 0 and ctx.mode != "router":
                return {"route": "plan", "plan_errors": errs, "replans": 1}
            reason = "tool_error" if any("failed" in e for e in errs) else "plan_failed"
            return self._escalate(state, reason, "; ".join(errs))
        if a.outcome == "escalated":
            return self._escalate(state, a.escalation_reason or "tool_error")
        if a.outcome == "out_of_scope":
            return self._end(state, cards.out_of_scope(a.notes, self.tables))
        sources, _ = cite(self.search, self._question(state), a)
        ctx.sources = sources
        if not a.figures:
            # nothing to word but a "no" (prohibited only): a code template, no writer call
            # (dev run 2: with no figures the writer kept inventing [F1] and copying dates)
            ctx.event("templated_answer", answer_kind=a.kind)
            c = cards.answered(a, prohibited_line(a, sources), [], sources, case.profile,
                               self.tables)  # fmt: skip
            return self._end(state, c, answered=True)
        return {"route": "write"}

    def _write(self, state: State) -> dict:
        ctx = current()
        a = ctx.assessment
        figures = cards.figure_rows(a.figures, a.lines)
        prev = state.get("writer_out")
        out = run_writer(
            self.chat,
            self._question(state),
            a,
            figures,
            ctx.sources,
            ctx.case.profile,
            problems=state.get("problems") or None,
            previous=WriterOut.model_validate(prev) if prev else None,
        )
        return {"writer_out": out.model_dump(), "route": "verify"}

    def _verify(self, state: State) -> dict:
        ctx = current()
        a, case = ctx.assessment, ctx.case
        out = WriterOut.model_validate(state["writer_out"])
        figures = cards.figure_rows(a.figures, a.lines)
        problems = check_wording(out, a, figures, ctx.sources, case.profile, case.basket,
                                 self.tables)  # fmt: skip
        if problems:
            ctx.event("verifier_failed", problems=problems)
            if state.get("rewrites", 0) == 0:
                return {"route": "write", "rewrites": 1, "problems": problems}
            return self._escalate(state, "verifier_failed", "; ".join(problems))
        review = (
            advisory_review(self.chat, out.working, ctx.sources)
            if self.settings.advisory_review
            else {"skipped": "off"}
        )
        c = cards.answered(a, out.bottom_line, out.working, ctx.sources, case.profile, self.tables)
        c.meta["review"] = review
        c.meta["retrieval_miss_recovered"] = [
            e["rule"] for e in ctx.events if e["event"] == "retrieval_miss_recovered"
        ]
        return self._end(state, c, answered=True)
