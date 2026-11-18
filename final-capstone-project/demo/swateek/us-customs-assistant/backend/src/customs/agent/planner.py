"""Planner, plan validation and the code router (plan §4.2).

The planner (one strict-JSON call) orders steps from a fixed vocabulary; `validate_plan` checks
the plan in code against the case after restrictions; an invalid plan goes back to the planner
once with the errors, then the router's plan is used (`plan_fallback`). The router is also the
whole planner in `router` mode. Escalation is decided by the calculators and the verifier, not
planned, so `escalate_to_human` is not in the planner's vocabulary.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from customs.agent.context import current
from customs.config import PROJECT_ROOT
from customs.llm.chat import ChatClient
from customs.tools.calc import Case

PROMPT = PROJECT_ROOT / "pack" / "prompts" / "planner.md"
MAX_TOKENS = 400

StepName = Literal[
    "check_restrictions",
    "determine_exemption",
    "compute_allowance",
    "compute_duty_excise",
    "lookup_state_rule",
    "search_regulations",
]
CHAIN = ["determine_exemption", "compute_allowance", "compute_duty_excise"]
LINE_STEPS = {"check_restrictions", "compute_allowance", "compute_duty_excise"}


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="ignore")
    step: StepName
    lines: list[int] = Field(default_factory=list)
    reason: str = Field(default="", max_length=200)


class Plan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    steps: list[PlanStep] = Field(max_length=10)


def describe_case(case: Case) -> str:
    """What the planner sees: the normalised profile and lines with their restriction status."""
    p = case.profile
    lines = []
    for nl in case.lines:
        bits = [f"line {nl.index}: {nl.line.item}"]
        if nl.volume_ml is not None:
            bits.append(f"{nl.volume_ml.normalize():f} ml")
        if nl.sticks is not None:
            bits.append(f"{nl.sticks} sticks")
        bits.append(f"status {nl.status}")
        lines.append(", ".join(bits))
    return (
        f"Traveller: age {p.age}, trip_hours {p.trip_hours}, arrived from "
        f"{p.arrived_directly_from}, exemption used in last 30 days "
        f"{p.exemption_used_last_30_days}, arrival state {p.arrival_state}.\n"
        "Basket:\n" + "\n".join(lines)
    )


def run_planner(
    chat: ChatClient, case: Case, errors: list[str] | None = None, stale: list[str] | None = None
) -> Plan:
    user = describe_case(case)
    if stale:
        user += f"\n\nThe traveller corrected a fact; these steps must be re-run: {stale}."
    if errors:
        user += "\n\nYour previous plan was invalid: " + "; ".join(errors) + ". Fix it."
    msgs = [
        {"role": "system", "content": PROMPT.read_text(encoding="utf-8").strip()},
        {"role": "user", "content": user},
    ]
    ctx = current()
    ctx.before_model_call()
    res = chat.complete(msgs, max_tokens=MAX_TOKENS, response_model=Plan, name="planner")
    ctx.after_model_call("planner", res)
    return res.parsed


def needs(case: Case) -> dict[str, bool]:
    state = (case.profile.arrival_state or "").upper()
    return {
        "chain": bool(case.admissible),
        "duty": bool(case.alcohol),
        "state": bool(case.alcohol) and state in case.t.states,
    }


def validate_plan(plan: Plan, case: Case) -> list[str]:
    """Errors in plain words (fed back to the planner); [] = valid. `case` has run restrictions."""
    steps = [s.step for s in plan.steps]
    errs: list[str] = []
    if not steps:
        return ["the plan is empty"]
    if len(steps) > 10:
        errs.append("more than 10 steps")
    dup = sorted({s for s in steps if steps.count(s) > 1})
    if dup:
        errs.append(f"repeated steps: {dup}")
    if steps[0] != "check_restrictions":
        errs.append("check_restrictions must be first")
    if steps[-1] != "search_regulations":
        errs.append("search_regulations must be last")
    n = needs(case)
    present = [s for s in CHAIN if s in steps]
    if n["chain"]:
        for s in CHAIN[:2]:
            if s not in steps:
                errs.append(f"{s} is missing")
        if n["duty"] and "compute_duty_excise" not in steps:
            errs.append("compute_duty_excise is missing (there is allowed alcohol)")
        order = [steps.index(s) for s in present]
        if order != sorted(order):
            errs.append("order must be determine_exemption, compute_allowance, compute_duty_excise")
    elif present:
        errs.append(f"no line is allowed in, so {present} must not run")
    if "lookup_state_rule" in steps and not n["state"]:
        errs.append("lookup_state_rule only with allowed alcohol and a state in CA, NY, FL, TX, IL")
    if n["state"] and "lookup_state_rule" not in steps:
        errs.append("lookup_state_rule is missing (alcohol arriving in a flagged state)")
    allowed = {nl.index for nl in case.admissible}
    known = {nl.index for nl in case.lines}
    for s in plan.steps:
        if s.lines and s.step not in LINE_STEPS:
            errs.append(f"{s.step} takes no lines")
        bad = [i for i in s.lines if i not in known]
        if bad:
            errs.append(f"{s.step}: no such lines {bad}")
        blocked = [i for i in s.lines if i in known and i not in allowed]
        if blocked and s.step != "check_restrictions":
            errs.append(f"{s.step}: lines {blocked} are not allowed in and get no calculation")
    return errs


def router_plan(case: Case) -> Plan:
    """The deterministic plan (router mode and the fallback)."""
    n = needs(case)
    steps = ["check_restrictions"]
    if n["chain"]:
        steps += ["determine_exemption", "compute_allowance"]
        if n["duty"]:
            steps.append("compute_duty_excise")
    if n["state"]:
        steps.append("lookup_state_rule")
    steps.append("search_regulations")
    return Plan(steps=[PlanStep(step=s, reason="router") for s in steps])


def plan_json(plan: Plan) -> list[dict]:
    return json.loads(plan.model_dump_json())["steps"]
