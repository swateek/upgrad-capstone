"""LLM planner + plan validator (CLAUDE.md architecture; ablation against the code router).

The planner sees the facts read by intake and a list of tools, and returns the tools to run, in
order. It never writes tool arguments: the executor fills them from the state. The validator
(code) checks the plan against an allowed-step graph before anything runs:

  - only known tools, no repeats, at most 10 steps, search_regulations last;
  - restrictions before any calculation (rule 4): normalise_units < check_restrictions <
    determine_exemption < compute_allowance < compute_duty_excise;
  - inputs present: whatif_optimise only (and first) for a what-if question; lookup_state_rule
    required when an arrival state is known (harmless, and allowed, otherwise);
  - escalate_to_human only after check_restrictions.

Invalid plan -> one repair with the errors fed back -> still invalid -> the code router's plan
(counted as a fallback in the trace).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from src.agent.intake import IntakeResult
from src.agent.llm_json import Usage, json_call
from src.agent.router import TOOLS
from src.baselines.answer import Strict

MAX_STEPS = 10
ToolName = Literal[
    "whatif_optimise",
    "normalise_units",
    "check_restrictions",
    "determine_exemption",
    "compute_allowance",
    "compute_duty_excise",
    "lookup_state_rule",
    "search_regulations",
    "escalate_to_human",
]
CALC_ORDER = [
    "normalise_units",
    "check_restrictions",
    "determine_exemption",
    "compute_allowance",
    "compute_duty_excise",
]

PLANNER = """You plan which tools a US customs assistant runs for one traveller, in order. The tools compute everything; you only choose and order them. Return JSON {"steps": [...], "reason": "..."}.

Tools:
- whatif_optimise: finds how many units of one product keep what is owed under a dollar target. Only when the traveller asks "how many can I bring and owe less than $X"; then it must be the first step.
- normalise_units: converts the stated quantities and sizes (bottles, cl, cartons, boxes) into litres and pieces. Every other tool reads its output, so it runs before all of them (only whatif_optimise may come before it).
- check_restrictions: prohibitions and limits (Cuban origin, under 21, commercial quantities). Runs right after normalise_units, before any exemption or duty step.
- determine_exemption: which exemption applies ($800 or $200) from the trip facts; reports missing facts.
- compute_allowance: what is duty-free and what is over, per item. Needs determine_exemption.
- compute_duty_excise: duty and federal excise on the part over. Needs compute_allowance.
- lookup_state_rule: the arrival state's own alcohol limits. Always when the arrival state is known.
- search_regulations: fetches the regulation text to cite. Always the last step.
- escalate_to_human: hand the case to an officer. Only when no tool can assess it.

Order rules: normalise_units -> check_restrictions -> determine_exemption -> compute_allowance -> compute_duty_excise; lookup_state_rule anywhere after normalise_units; search_regulations last. At most 10 steps, each tool at most once."""


class Plan(Strict):
    steps: list[ToolName] = Field(max_length=MAX_STEPS)
    reason: str = Field("", description="One short sentence")


def describe(facts: IntakeResult) -> str:
    p = facts.profile
    out = ["Facts read from the question:"]
    out.append(f"- age: {p.age if p.age is not None else 'not stated'}")
    out.append(
        f"- trip: {f'{p.trip.value:g} {p.trip.unit}' if p.trip else 'not stated'}"
    )
    out.append(f"- arriving directly from: {p.direct_arrival_from or 'not stated'}")
    out.append(f"- arrival state: {p.arrival_state or 'not stated'}")
    for i, b in enumerate(facts.basket, start=1):
        out.append(
            f"- item {i}: {b.quantity.value:g} {b.quantity.unit} {b.item} ({b.category}, {b.type}), origin {b.origin or 'not stated'}"
        )
    if facts.owe_less_than_usd:
        out.append(
            f"- what-if: how many can they bring and owe less than ${facts.owe_less_than_usd:g}"
        )
    return "\n".join(out)


def validate(steps: list[str], facts: IntakeResult) -> list[str]:
    errors: list[str] = []
    if not steps:
        return ["the plan is empty"]
    if len(steps) > MAX_STEPS:
        errors.append(f"at most {MAX_STEPS} steps")
    unknown = [s for s in steps if s not in TOOLS]
    if unknown:
        errors.append(f"unknown tools {unknown}")
    dup = sorted({s for s in steps if steps.count(s) > 1})
    if dup:
        errors.append(f"each tool at most once (repeated: {dup})")
    if steps[-1] != "search_regulations":
        errors.append("search_regulations must be the last step")
    whatif = bool(facts.owe_less_than_usd)
    if whatif and steps[0] != "whatif_optimise":
        errors.append("a what-if question starts with whatif_optimise")
    if not whatif and "whatif_optimise" in steps:
        errors.append("whatif_optimise only for a what-if question")
    if "escalate_to_human" not in steps:
        missing = [s for s in CALC_ORDER if s not in steps]
        if missing:
            errors.append(f"missing steps {missing}")
    present = [s for s in CALC_ORDER if s in steps]
    if [s for s in steps if s in CALC_ORDER] != present:
        errors.append(
            f"calculation steps must run in this order: {' -> '.join(CALC_ORDER)}"
        )
    if "escalate_to_human" in steps and (
        "check_restrictions" not in steps
        or steps.index("escalate_to_human") < steps.index("check_restrictions")
    ):
        errors.append("escalate_to_human only after check_restrictions")
    if facts.profile.arrival_state and "lookup_state_rule" not in steps:
        errors.append("the arrival state is known: include lookup_state_rule")
    return errors


def propose(
    llm: Any, usage: Usage, facts: IntakeResult, errors: list[str] | None = None
) -> Plan:
    msgs = [
        {"role": "system", "content": PLANNER},
        {"role": "user", "content": describe(facts)},
    ]
    if errors:
        msgs.append(
            {
                "role": "user",
                "content": "Your previous plan was invalid:\n"
                + "\n".join(f"- {e}" for e in errors)
                + "\nReturn a corrected plan.",
            }
        )
    return json_call(llm, usage, Plan, msgs, stage="planner", max_tokens=200)
