"""Plan executor and the code router (CLAUDE.md architecture; the ablation baseline for the planner).

A plan is an ordered list of tool names. `execute()` runs any valid plan, filling every tool's
arguments from the state (the model never writes tool arguments: it copies numbers badly,
COMPENSATIONS row 3). The code router is one fixed plan:

    normalise_units -> check_restrictions -> determine_exemption -> (clarify?) -> (escalate?)
      -> compute_allowance -> compute_duty_excise -> lookup_state_rule -> search_regulations
    what-if questions: whatif_optimise first, then the same chain at the answer's quantity

The LLM planner (src/agent/planner.py) proposes a plan instead; the validator checks it and the
same executor runs it, so a difference in score belongs to the plan alone.

Restrictions run before any calculation (rule 4). Missing facts come from the tools, in the SPEC 5.2
order, never from the model. The router also collects the citations of the rules each tool applied,
for search_regulations to fetch by id (docs/RETRIEVAL.md): the first two per rule, because a mixed
basket can apply more rules than the 5-clause budget holds.
"""

# ruff: noqa: B023  (each lambda passed to _call runs at once, inside its loop iteration)

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from src.schemas import (
    Allowance,
    Amount,
    BasketLine,
    DutyExcise,
    Exemption,
    NormalisedLine,
    Profile,
    Restrictions,
    StateFlag,
    WhatIf,
)
from src.tools import (
    ToolError,
    check_restrictions,
    compute_allowance,
    compute_duty_excise,
    determine_exemption,
    lookup_state_rule,
    normalise_units,
    whatif_optimise,
)
from src.tools.check_restrictions import Args as RArgs
from src.tools.common import order_missing, rules
from src.tools.compute_allowance import Args as AArgs
from src.tools.compute_duty_excise import Args as DArgs
from src.tools.determine_exemption import Args as EArgs
from src.tools.lookup_state_rule import Args as SArgs
from src.tools.normalise_units import Args as NArgs
from src.tools.whatif_optimise import Args as WArgs

PER_RULE = 2  # citations passed per applied rule
TOOLS = (
    "whatif_optimise",
    "normalise_units",
    "check_restrictions",
    "determine_exemption",
    "compute_allowance",
    "compute_duty_excise",
    "lookup_state_rule",
    "search_regulations",
    "escalate_to_human",
)
ROUTER_PLAN = [
    "normalise_units",
    "check_restrictions",
    "determine_exemption",
    "compute_allowance",
    "compute_duty_excise",
    "lookup_state_rule",
    "search_regulations",
]
ROUTER_WHATIF_PLAN = ["whatif_optimise", *ROUTER_PLAN]


class PlanError(Exception):
    """A plan step ran without its inputs (the validator should have caught it)."""


STATUS_TO_LINE_TYPE = {
    "prohibited": "prohibited",
    "declare_detention_risk": "declare_detention_risk",
    "relinquish_excess": "relinquish_excess",
    "exempt": "nothing_to_pay",
}


@dataclass
class RouteResult:
    outcome: Literal["answered", "clarify", "escalated"]
    missing: list[str] = field(default_factory=list)
    rule_id: str | None = None
    message: str | None = None
    lines: list[NormalisedLine] = field(default_factory=list)
    restrictions: Restrictions | None = None
    exemption: Exemption | None = None
    allowance: Allowance | None = None
    duty: DutyExcise | None = None
    state_flag: StateFlag | None = None
    whatif: WhatIf | None = None
    line_types: list[str] = field(default_factory=list)  # bottom line per basket line
    citations: list[str] = field(default_factory=list)  # rules applied, in order
    trace: list[dict] = field(default_factory=list)  # tool name + compact output
    plan: list[str] = field(default_factory=list)
    tool_steps: int = 0  # tools actually run (search counted by the pipeline)
    reused: list[str] = field(
        default_factory=list
    )  # steps taken from the previous turn

    def tool_outputs(self) -> list[object]:
        return [
            x
            for x in (
                self.restrictions,
                self.exemption,
                self.allowance,
                self.duty,
                self.state_flag,
                self.whatif,
            )
            if x is not None
        ]


def _cite(out: list[str], ids: list[str], n: int = PER_RULE) -> None:
    added = 0
    for c in ids:
        if added >= n:
            break
        if c not in out:
            out.append(c)
            added += 1


def _rule_citations(rule_id: str) -> list[str]:
    return next(
        (x.get("citations", []) for x in rules()["restrictions"] if x["id"] == rule_id),
        [],
    )


def _log(r: RouteResult, tool: str, output: object) -> None:
    dump = (
        output.model_dump(mode="json", exclude_none=True)
        if hasattr(output, "model_dump")
        else output
    )
    r.trace.append({"tool": tool, "output": dump})


def _need(cond: object, step: str, what: str) -> None:
    if not cond:
        raise PlanError(f"{step} needs {what} first")


def _finish(r: RouteResult) -> RouteResult:
    """Bottom line per item once the allowance (and duty, if anything is dutiable) is known."""
    al, de = r.allowance, r.duty
    if al is None:
        return r
    owed = {d.line: d.total_usd for d in (de.lines if de else [])}
    r.line_types = []
    for a in al.lines:
        if a.status in ("partly_exempt", "dutiable"):
            r.line_types.append(
                "owe" if owed.get(a.line, Decimal(0)) > 0 else "nothing_to_pay"
            )
        else:
            r.line_types.append(STATUS_TO_LINE_TYPE[a.status])
    return r


ITEM_FACTS = {"size", "count"}


def _placeholder(basket: list[BasketLine]) -> list[BasketLine]:
    """Stand-ins for unreadable item facts, only to find which trip facts are also missing."""
    out = []
    for b in basket:
        upd: dict = {}
        if b.category == "alcohol" and b.size is None:
            upd["size"] = Amount(value=750, unit="ml")
        if b.category == "tobacco":
            upd["quantity"] = b.quantity.model_copy(
                update={"unit": "cigar" if b.type == "cigars" else "cigarette"}
            )
        out.append(b.model_copy(update=upd) if upd else b)
    return out


def execute(
    profile: Profile,
    basket: list[BasketLine],
    plan: list[str],
    owe_less_than_usd: float | None = None,
    reuse: dict | None = None,
) -> RouteResult:
    """Run a plan. Stops early on clarify / escalate / everything prohibited, as the rules say.

    When an item fact (size, count) is missing, the trip facts that are also missing are found by
    running the plan once more with stand-in values, so every missing fact is asked in one
    message (SPEC 5.2, amended Day 7). The stand-in run's answer is never used.
    """
    r = _execute_once(profile, basket, plan, owe_less_than_usd, reuse)
    if r.outcome == "clarify" and ITEM_FACTS & set(r.missing):
        probe = _execute_once(profile, _placeholder(basket), plan, owe_less_than_usd)
        if probe.outcome == "clarify":
            r.missing = order_missing(list(dict.fromkeys(r.missing + probe.missing)))
    return r


def _execute_once(
    profile: Profile,
    basket: list[BasketLine],
    plan: list[str],
    owe_less_than_usd: float | None = None,
    reuse: dict | None = None,
) -> RouteResult:
    r = RouteResult(outcome="answered", plan=list(plan))
    try:
        return _execute(profile, list(basket), plan, owe_less_than_usd, r, reuse)
    except ToolError as e:
        if e.code == "missing_fact":
            r.outcome, r.missing = "clarify", order_missing(e.missing)
        else:
            r.outcome, r.rule_id, r.message = (
                "escalated",
                e.rule_id or e.code,
                e.message,
            )
            _cite(r.citations, e.citations)
        return r


def _call(r: RouteResult, step: str, reuse: dict, fn: Callable, log: bool = True):
    """Run one tool, or take its output from the previous turn when the facts it depends on did
    not change (a correction replans only the steps after the changed fact)."""
    if step in reuse:
        out = reuse[step]
        r.reused.append(step)
        r.trace.append({"tool": step, "reused": True})
        return out
    out = fn()
    r.tool_steps += 1
    if log:
        _log(
            r,
            step,
            [x.model_dump(mode="json", exclude_none=True) for x in out]
            if isinstance(out, list)
            else out,
        )
    return out


def _execute(
    profile: Profile,
    basket: list[BasketLine],
    plan: list[str],
    owe_less_than_usd: float | None,
    r: RouteResult,
    reuse: dict | None = None,
) -> RouteResult:
    reuse = reuse or {}
    rs = ex = al = None
    lines: list[NormalisedLine] | None = None
    for step in plan:
        if step == "whatif_optimise":
            _need(owe_less_than_usd, step, "a what-if target")
            product = basket[0]
            w = _call(
                r,
                step,
                reuse,
                lambda: whatif_optimise(
                    WArgs(
                        profile=profile,
                        product=product,
                        owe_less_than_usd=owe_less_than_usd,
                    )
                ),
            )
            r.whatif = w
            basket = [
                product.model_copy(
                    update={
                        "quantity": product.quantity.model_copy(
                            update={"value": w.max_units}
                        )
                    }
                )
            ]
        elif step == "normalise_units":
            lines = _call(r, step, reuse, lambda: normalise_units(NArgs(basket=basket)))
            r.lines = lines
        elif step == "check_restrictions":
            _need(lines is not None, step, "normalise_units")
            rs = _call(
                r,
                step,
                reuse,
                lambda: check_restrictions(RArgs(profile=profile, lines=lines)),
            )
            r.restrictions = rs
            for h in rs.hits:
                _cite(r.citations, h.citations)
            if lines and set(rs.prohibited_lines) >= {ln.index for ln in lines}:
                # everything is prohibited: no exemption fact can change the answer (SPEC 5.2)
                r.line_types = ["prohibited"] * len(lines)
                r.outcome = "answered"
                return r
        elif step == "determine_exemption":
            _need(rs is not None, step, "check_restrictions")  # rule 4
            ex = _call(
                r,
                step,
                reuse,
                lambda: determine_exemption(EArgs(profile=profile, lines=lines)),
            )
            r.exemption = ex
            missing = order_missing(rs.missing + ex.missing)
            if missing:
                r.outcome, r.missing = "clarify", missing
                return r
            if rs.escalate:
                hit = next(h for h in rs.hits if h.outcome == "escalate")
                r.outcome, r.rule_id, r.message = "escalated", hit.rule_id, hit.message
                return r
            _cite(r.citations, ex.citations)
        elif step == "compute_allowance":
            _need(ex is not None, step, "determine_exemption")
            al = _call(
                r,
                step,
                reuse,
                lambda: compute_allowance(
                    AArgs(exemption=ex, restrictions=rs, lines=lines)
                ),
            )
            r.allowance = al
            for rid in dict.fromkeys(a.rule_id for a in al.lines if a.rule_id):
                _cite(r.citations, _rule_citations(rid))  # rules applied per line
            esc = next((a for a in al.lines if a.status == "escalate"), None)
            if esc:
                r.outcome, r.rule_id, r.message = "escalated", esc.rule_id, esc.message
                return r
        elif step == "compute_duty_excise":
            _need(al is not None, step, "compute_allowance")
            de = _call(
                r,
                step,
                reuse,
                lambda: compute_duty_excise(
                    DArgs(profile=profile, lines=lines, allowance=al)
                ),
            )
            r.duty = de
            _cite(r.citations, de.citations)
        elif step == "lookup_state_rule":
            sf = _call(
                r,
                step,
                reuse,
                lambda: lookup_state_rule(SArgs(arrival_state=profile.arrival_state)),
                log=False,
            )
            if sf:
                r.state_flag = sf
                _log(r, step, sf)
                _cite(r.citations, sf.citations, 1)
        elif step == "escalate_to_human":
            r.outcome, r.rule_id = "escalated", r.rule_id or "planner_escalated"
            r.message = r.message or "The planner could not assess this with the tools."
            return r
        elif step == "search_regulations":
            continue  # run by the pipeline, with the citations collected here
        else:
            raise PlanError(f"unknown tool {step!r}")
    if r.whatif:
        r.line_types = []  # a what-if has no bottom line per item
        return r
    return _finish(r)


def route(
    profile: Profile,
    basket: list[BasketLine],
    owe_less_than_usd: float | None = None,
) -> RouteResult:
    """The code router: the fixed plan."""
    plan = ROUTER_WHATIF_PLAN if owe_less_than_usd else ROUTER_PLAN
    return execute(profile, basket, plan, owe_less_than_usd)
