"""One question end to end with the code router (agent v0):

    guard -> intake (LLM) -> router (tools in fixed order) -> search_regulations -> sanitise
      -> writer (LLM) -> verifier (code + LLM) -> [writer retry once] -> answered | escalated
    clarify / refused / escalated short-circuit with code-written messages.

Returns an AgentRun whose record matches eval/score.py (answer + retrieved_ids) and carries the full
answer card and a trace of every step.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.agent import card as C
from src.agent.intake import (
    extract,
    ground_in_question,
    normalise_countries,
    origin_from_question,
    sizes_from_question,
)
from src.agent.llm_json import StepError, Usage
from src.agent.planner import propose, validate
from src.agent.router import (
    ROUTER_PLAN,
    ROUTER_WHATIF_PLAN,
    RouteResult,
    execute,
    route,
)
from src.agent.verifier import tool_json, verify
from src.agent.writer import write
from src.baselines.answer import Answer, LineResult, WhatIfAnswer
from src.safety.guard import check_question, sanitise_clause
from src.schemas import Clause, Clauses
from src.tools import escalate_to_human
from src.tools.escalate_to_human import Args as EscArgs
from src.tools.search_regulations import Args as SearchArgs

FACT_QUESTIONS = {
    "age": "How old are you?",
    "trip_length": "How long were you outside the US (hours or days), and which country did you arrive from?",
    "exemption_used_last_30_days": "Have you used your duty-free exemption (or been abroad) in the last 30 days?",
    "origin": "Where was {item} made?",
    "abv": "What is the alcohol content (ABV %) of {item}?",
    "size": "What size is each container of {item}?",
    "unit_price": "What did you pay for {item}?",
    "count": "How many {item} do you have?",
}

SearchFn = Callable[[SearchArgs], Clauses]

# Hard budget per question (CLAUDE.md; course guardrail: at most 10 steps per query).
# A step = one tool run (search included). Model calls are bounded by the token budget.
MAX_TOOL_STEPS = 10
MAX_TOKENS = 12_000


@dataclass
class AgentRun:
    answer: Answer | None = None
    error: str | None = None
    reason: str | None = None  # refused / escalated: why
    usage: Usage = field(default_factory=Usage)
    retrieved_ids: list[str] | None = None
    card: dict = field(default_factory=dict)
    trace: list[dict] = field(default_factory=list)
    tool_steps: int = 0
    plan_fallback: bool | None = (
        None  # planner mode: True if the router's plan was used
    )

    def record(self, item_id: str, mode: str = "router") -> dict:
        return {
            "id": item_id,
            "strategy": mode,
            "answer": json.loads(self.answer.model_dump_json())
            if self.answer
            else None,
            "error": self.error,
            "reason": self.reason,
            "tool_steps": self.tool_steps,
            "plan_fallback": self.plan_fallback,
            "calls": self.usage.calls,
            "tokens": self.usage.tokens,
            "retrieved_ids": self.retrieved_ids,
            "card": self.card,
            "trace": self.trace,
            "steps": self.usage.steps,
        }


def _over_budget(run: AgentRun, what: str) -> AgentRun:
    run.reason = "budget_exceeded"
    run.trace.append({"step": "budget", "exceeded": what})
    run.answer = Answer(
        outcome="escalated",
        message="This question needs more work than one estimate allows. Declare everything; a CBP officer will assess it.",
    )
    return run


def _plan(run: AgentRun, llm: Any, facts) -> list[str]:
    """LLM plan, validated; one repair; else the code router's plan (a fallback)."""
    fixed = ROUTER_WHATIF_PLAN if facts.owe_less_than_usd else ROUTER_PLAN
    errors: list[str] | None = None
    for attempt in range(2):
        try:
            p = propose(llm, run.usage, facts, errors)
        except StepError as e:
            run.trace.append({"step": "planner", "attempt": attempt, "error": str(e)})
            break
        errors = validate(list(p.steps), facts)
        run.trace.append(
            {
                "step": "planner",
                "attempt": attempt,
                "plan": list(p.steps),
                "reason": p.reason,
                "errors": errors,
            }
        )
        if not errors:
            run.plan_fallback = False
            return list(p.steps)
    run.plan_fallback = True
    run.trace.append({"step": "planner", "fallback": "code router plan"})
    return fixed


def _clarify(run: AgentRun, missing: list[str], items: list[str]) -> AgentRun:
    item = items[0] if items else "the item"
    qs = [FACT_QUESTIONS.get(f, f).format(item=item) for f in missing]
    msg = "To work this out I need a little more: " + " ".join(qs)
    run.answer = Answer(outcome="clarify", clarify_facts=missing, message=msg)
    run.card = {"clarify": qs}
    return run


def _search(
    search: SearchFn, run: AgentRun, question: str, ids: list[str], inject: dict | None
) -> list[Clause]:
    t0 = time.perf_counter()
    found = search(SearchArgs(query=question, citation_ids=ids))
    clauses = list(found.clauses)
    if (
        inject
    ):  # injection_doc scenarios: the harness plants a passage among the results
        clauses.insert(
            0,
            Clause(
                citation_id=inject["doc_id"],
                chunk_id=f"{inject['doc_id']}#01",
                heading="",
                text=inject["text"],
                authority="agency_guidance",
                found_by="search",
                rank=1,
            ),
        )
    kept, dropped = [], []
    for c in clauses:
        ok, why = sanitise_clause(c.text)
        (kept if ok else dropped).append(
            c if ok else {"citation_id": c.citation_id, "why": why}
        )
    run.trace.append(
        {
            "step": "search_regulations",
            "by_id": ids,
            "retrieved": [c.citation_id for c in kept],
            "not_found": found.not_found,
            "dropped_by_sanitiser": dropped,
            "method": found.method,
            "ms": round((time.perf_counter() - t0) * 1000),
        }
    )
    run.retrieved_ids = list(dict.fromkeys(c.citation_id for c in kept))
    return kept


def answer_question(
    question: str,
    *,
    llm: Any,
    search: SearchFn,
    inject: dict | None = None,
    verify_with_llm: bool = True,
    mode: str = "router",
) -> AgentRun:
    """mode: "router" (fixed plan) or "planner" (LLM plan, validated; router plan as fallback)."""
    run = AgentRun()
    try:
        return _answer(run, question, llm, search, inject, verify_with_llm, mode)
    except Exception as e:  # noqa: BLE001 - endpoint or tool failure: record it, escalate
        run.error = f"{type(e).__name__}: {e}"
        run.reason = run.reason or "error"
        run.answer = Answer(
            outcome="escalated",
            message="I couldn't complete this estimate. Declare everything; a CBP officer will assess it.",
        )
        return run


def _answer(
    run: AgentRun,
    question: str,
    llm: Any,
    search: SearchFn,
    inject: dict | None,
    verify_with_llm: bool,
    mode: str = "router",
) -> AgentRun:
    # 1. guard (code)
    g = check_question(question)
    run.trace.append({"step": "guard", "action": g.action, "reason": g.reason})
    if g.action == "refuse":
        run.reason = g.reason
        run.answer = Answer(outcome="refused", message=g.message)
        return run

    # 2. intake (LLM)
    try:
        facts = extract(llm, run.usage, question)
    except StepError as e:
        run.reason, run.error = "intake_failed", str(e)
        run.answer = Answer(
            outcome="escalated",
            message="I couldn't read the details of this question. Declare everything; an officer decides.",
        )
        return run
    facts, changed = normalise_countries(facts)  # names -> ISO codes, before any tool
    facts, stated = origin_from_question(facts, question)  # "Cuban cigars" -> CU
    changed += stated
    facts, sized = sizes_from_question(
        facts, question
    )  # "75cl" missed; no invented sizes
    changed += sized
    facts, dropped = ground_in_question(
        facts, question
    )  # no guessed age or trip length
    run.trace.append(
        {
            "step": "intake",
            "output": facts.model_dump(mode="json", exclude_none=True),
            "countries_normalised": changed,
            "dropped_unstated": dropped,
        }
    )
    if facts.request_kind != "assess":
        run.reason = (
            facts.request_kind
            if facts.request_kind != "out_of_scope"
            else "out_of_scope_other_goods"
        )
        from src.safety.guard import MESSAGES  # same wording as the guard

        key = (
            "out_of_scope"
            if facts.request_kind == "out_of_scope"
            else facts.request_kind
        )
        run.answer = Answer(
            outcome="refused",
            message=MESSAGES[key].format(what="those goods"),
        )
        return run
    # an item of type "other" is not alcohol or tobacco, whatever category the model gave it
    basket = [b for b in facts.basket if b.category != "other" and b.type != "other"]
    other = len(basket) < len(facts.basket) or g.other_goods
    if not basket:
        if other:
            run.reason = "out_of_scope_other_goods"
            run.answer = Answer(
                outcome="refused",
                message="This assistant only covers alcohol and tobacco. See CBP's traveller guidance at cbp.gov for other goods.",
            )
            return run
        run.answer = Answer(
            outcome="clarify",
            clarify_facts=["count"],
            message="What are you bringing home? Tell me each bottle or tobacco product, how many, their size and what you paid.",
        )
        run.card = {
            "clarify": [
                "What are you bringing home: which bottles or tobacco, how many, what size and what price?"
            ]
        }
        return run

    # 3. plan: the code router's fixed plan, or the LLM planner's (validated; router as fallback)
    if mode == "planner":
        plan = _plan(run, llm, facts.model_copy(update={"basket": basket}))
        r: RouteResult = execute(facts.profile, basket, plan, facts.owe_less_than_usd)
    else:
        r = route(facts.profile, basket, facts.owe_less_than_usd)
    run.tool_steps = r.tool_steps + 1  # + search_regulations
    run.trace.append(
        {"step": "executor", "plan": r.plan, "outcome": r.outcome, "tools": r.trace}
    )
    if (
        run.tool_steps > MAX_TOOL_STEPS
    ):  # cannot happen with a validated plan; kept as a hard stop
        return _over_budget(run, f"{run.tool_steps} tool steps")
    if r.outcome == "clarify":
        return _clarify(run, r.missing, [b.item for b in basket])

    # 4. retrieval: the rules the tools applied (by id) + search
    clauses = _search(search, run, question, r.citations, inject)
    cited_by_rule = [c.citation_id for c in clauses if c.found_by == "citation_id"]

    if r.outcome == "escalated":
        note = escalate_to_human(
            EscArgs(
                reason=r.message or r.rule_id or "officer decision",
                profile=facts.profile,
                basket=basket,
            )
        )
        run.reason = r.rule_id
        run.answer = Answer(
            outcome="escalated", citations=cited_by_rule, message=note.summary
        )
        run.card = {
            "escalation": note.model_dump(mode="json"),
            "citations": cited_by_rule,
        }
        return run

    # 5. answer card (code) + writer (LLM) + verifier (code + LLM), one retry
    facts_list = C.facts_relied_on(
        facts.profile, r.lines, age_21_plus=any("21 or over" in d for d in dropped)
    )
    working = C.working(r)
    result = C.bottom_line_items(r)
    if other:
        working.append(
            "Other goods you mentioned are not assessed here, but they count toward the same $800 exemption."
        )
    tools_json = tool_json(r.tool_outputs())
    total = r.duty.total_usd if r.duty and r.duty.lines else None
    feedback: list[str] | None = None
    out = None
    for attempt in range(2):
        if run.usage.tokens > MAX_TOKENS:
            return _over_budget(run, f"{run.usage.tokens} tokens")
        try:
            out = write(
                llm,
                run.usage,
                question=question,
                result=result,
                working=working,
                facts=facts_list,
                clauses=clauses,
                feedback=feedback,
            )
        except StepError as e:
            feedback = [str(e)]
            out = None
            continue
        feedback = verify(
            out,
            n_clauses=len(clauses),
            tool_json=tools_json + "\n" + "\n".join(result + working),
            facts_text="\n".join(facts_list),
            question=question,
            clause_texts=[c.text for c in clauses],
            total_owed=total,
            llm=llm if verify_with_llm else None,
            usage=run.usage,
        )
        run.trace.append({"step": "verifier", "attempt": attempt, "problems": feedback})
        if not feedback:
            break
    if feedback or out is None:
        run.reason = "verifier_failed"
        run.answer = Answer(
            outcome="escalated",
            citations=cited_by_rule,
            message="I couldn't produce a checked estimate. Declare everything; a CBP officer will assess it.",
        )
        run.card = {"verifier_problems": feedback}
        return run

    # citations: the rules the tools applied (deterministic) + the clauses the writer used
    used = [clauses[i - 1].citation_id for i in out.sources]
    citations = list(dict.fromkeys(cited_by_rule + used))
    date = C.as_of(
        Clauses(
            query=question,
            clauses=clauses,
            retrieved_ids=run.retrieved_ids or [],
            method="",
        )
    )
    disclaimer = C.disclaimer(date)
    run.answer = Answer(
        outcome="answered",
        bottom_line=[
            LineResult(line=n.index, item=n.line.item, type=t)
            for n, t in zip(r.lines, r.line_types, strict=False)
        ],
        duty_usd=float(r.duty.duty_usd) if r.duty else None,
        excise_usd=float(r.duty.excise_usd) if r.duty else None,
        total_usd=float(r.duty.total_usd) if r.duty else None,
        whatif=WhatIfAnswer(
            max_units=r.whatif.max_units, owed_usd=float(r.whatif.owed_usd)
        )
        if r.whatif
        else None,
        citations=citations,
        state_flag=r.state_flag.state if r.state_flag else None,
        message=f"{out.bottom_line} {out.explanation} {disclaimer}",
    )
    by_id = {c.citation_id: c for c in clauses}
    owed = {d.line: float(d.total_usd) for d in (r.duty.lines if r.duty else [])}
    run.card = {
        "bottom_line": out.bottom_line,
        "items": [
            {
                "line": n.index,
                "item": n.line.item,
                "type": t,
                "owed_usd": owed.get(n.index),
            }
            for n, t in zip(r.lines, r.line_types, strict=False)
        ],
        "result": result,
        "explanation": out.explanation,
        "working": working,
        "facts_relied_on": facts_list,
        "assumptions": [],
        "citations": [
            {"id": c, "as_of": by_id[c].as_of, "url": by_id[c].source_url}
            for c in citations
            if c in by_id
        ],
        "state_flag": r.state_flag.model_dump(mode="json") if r.state_flag else None,
        "disclaimer": disclaimer,
    }
    return run
