"""The executor's tools (SPEC §8). Each wraps one calculator step on the shared Case.

Contract (as in the reference app): a Pydantic input; a dict result; failures reported as
{"error": str, "retryable": bool}, never raised. Results carry `rule_refs` and `figures`, the only
numbers an answer may show. Calculators read the profile and basket from the Case (graph state),
so their arguments are at most line indices.

`requires` lists the steps a tool needs first; the plan validator (agent step) checks plans
against it, and calling a tool out of order returns a non-retryable error.
`search_regulations` joins in the agent step, once the index exists.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from customs.tools.calc import (
    Case,
    _figures,
    fmt,
    step_allowance,
    step_caps,
    step_duty_excise,
    step_exemption,
    step_flags,
    step_normalise,
    step_restrictions,
)


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Lines(BaseModel):
    """Optional subset of basket lines (1-based); empty = all lines."""

    model_config = ConfigDict(extra="forbid")
    lines: list[int] = Field(default_factory=list)


class EscalateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=200)


def _err(msg: str, retryable: bool = False) -> dict:
    return {"error": msg, "retryable": retryable}


def _figs(case: Case, prefixes: tuple[str, ...]) -> list[dict]:
    return [f.model_dump() for f in _figures(case) if f.name.startswith(prefixes)]


def normalise_units(case: Case, args: NoArgs) -> dict:
    step_normalise(case)
    return {
        "lines": [
            {
                "line": nl.index,
                "item": nl.line.item,
                "volume_ml": None if nl.volume_ml is None else fmt(nl.volume_ml),
                "sticks": nl.sticks,
                "abv": None if nl.abv is None else fmt(nl.abv),
                "status": nl.status,
            }
            for nl in case.lines
        ],
        "defaults_used": case.defaults_used,
        "rule_refs": [],
        "figures": [],
    }


def check_restrictions(case: Case, args: Lines) -> dict:
    step_restrictions(case)
    rows = [
        {"line": nl.index, "status": nl.status, "where": nl.prohibited_where}
        for nl in case.lines
        if not args.lines or nl.index in args.lines
    ]
    refs = sorted(
        {f"R4:{nl.prohibited_where}" for nl in case.lines if nl.status == "prohibited"}
        | (
            {"R12", "R4:third_country"}
            if any(nl.status == "possibly_cuban" for nl in case.lines)
            else set()
        )
    )
    return {"lines": rows, "scope": case.scope, "rule_refs": refs, "figures": []}


def determine_exemption(case: Case, args: NoArgs) -> dict:
    step_exemption(case)
    refs = [r for r in case.rule_refs if r in ("R9", "R1")]
    return {
        "exemption_usd": case.exemption,
        "why": "48h+ or direct from Mexico, not used in 30 days"
        if case.exemption == 800
        else "under 48h (not Mexico) or used in the last 30 days",
        "rule_refs": refs,
        "figures": [{"name": "exemption_usd", "value": str(case.exemption), "unit": "usd"}],
    }


def compute_allowance(case: Case, args: Lines) -> dict:
    step_allowance(case)
    return {
        "alcohol_allowance_ml": None
        if case.alcohol_allowance_ml is None
        else fmt(case.alcohol_allowance_ml),
        "all_or_nothing_triggered": case.all_or_nothing_triggered,
        "rule_refs": [r for r in case.rule_refs if r in ("R1", "R2", "R3", "R5", "R6", "R11")],
        "figures": _figs(
            case, ("alcohol_allowance_ml", "exempt_", "dutiable_ml_", "excess_sticks_")
        ),
    }


def compute_duty_excise(case: Case, args: Lines) -> dict:
    step_duty_excise(case)
    step_caps(case)
    if case.escalation:
        return {
            "escalate": case.escalation,
            "rule_refs": [r for r in case.rule_refs if r == "R10"],
            "figures": [],
        }
    return {
        "rule_refs": [r for r in case.rule_refs if r in ("R7", "R8")],
        "figures": _figs(
            case,
            (
                "dutiable_value_usd_",
                "duty_rate_",
                "duty_usd_",
                "excise_usd_",
                "duty_total",
                "excise_total",
                "total_owed",
            ),
        ),
    }


def lookup_state_rule(case: Case, args: NoArgs) -> dict:
    step_flags(case)
    state = (case.profile.arrival_state or "").upper()
    row = case.t.states.get(state)
    if not case.alcohol:
        return {"flag": None, "rule_refs": [], "figures": []}
    if row is None:
        return {"flag": None, "note": "generic_state_note", "rule_refs": [], "figures": []}
    return {
        "flag": row["flag"],
        "cites": row["cites"],
        "rule_refs": [f"state:{state}"],
        "figures": [],
    }


def escalate_to_human(case: Case, args: EscalateArgs) -> dict:
    p = case.profile
    facts = {
        "age": p.age,
        "trip_hours": p.trip_hours,
        "arrived_directly_from": p.arrived_directly_from,
        "exemption_used_last_30_days": p.exemption_used_last_30_days,
        "arrival_state": p.arrival_state,
        "lines": [nl.line.model_dump(exclude_none=True) for nl in case.lines],
    }
    return {
        "handoff": (
            "We couldn't give you a reliable estimate for this one. Please declare everything and "
            "ask a CBP officer, or contact the CBP Information Center or your port of entry before "
            "you travel."
        ),
        "reason": args.reason,
        "facts_relied_on": facts,
        "rule_refs": [],
        "figures": [],
    }


ToolFn = Callable[[Case, Any], dict]

TOOLS: dict[str, dict[str, Any]] = {
    "normalise_units": {
        "fn": normalise_units,
        "input": NoArgs,
        "requires": [],
        "description": "Convert quantities to ml and sticks; fill stated defaults.",
    },
    "check_restrictions": {
        "fn": check_restrictions,
        "input": Lines,
        "requires": ["normalise"],
        "description": "Cuban origin, ambiguous brands, Russian alcohol, other goods, out-of-scope travellers.",
    },
    "determine_exemption": {
        "fn": determine_exemption,
        "input": NoArgs,
        "requires": ["normalise", "restrictions"],
        "description": "$800 or $200 exemption (48 hours, Mexico, 30 days).",
    },
    "compute_allowance": {
        "fn": compute_allowance,
        "input": Lines,
        "requires": ["exemption"],
        "description": "Exempt vs dutiable alcohol and tobacco; 2 L rule; under 21; all-or-nothing.",
    },
    "compute_duty_excise": {
        "fn": compute_duty_excise,
        "input": Lines,
        "requires": ["allowance"],
        "description": "Duty (3% / 4% / free for partner products) and federal excise on dutiable alcohol.",
    },
    "lookup_state_rule": {
        "fn": lookup_state_rule,
        "input": NoArgs,
        "requires": ["restrictions"],
        "description": "Arrival-state alcohol flag and its source.",
    },
    "escalate_to_human": {
        "fn": escalate_to_human,
        "input": EscalateArgs,
        "requires": [],
        "description": "Hand-off note: what is known, where to ask.",
    },
}


def run_tool(case: Case, name: str, raw_args: dict | None = None) -> dict:
    """Validate arguments, check prerequisites, run; never raises."""
    spec = TOOLS.get(name)
    if spec is None:
        return _err(f"unknown tool {name!r}; tools: {sorted(TOOLS)}")
    try:
        args = spec["input"].model_validate(raw_args or {})
    except ValidationError as err:
        return _err(f"invalid arguments for {name}: {err.errors()[0]['msg']}", retryable=True)
    missing = [r for r in spec["requires"] if r not in case.done]
    if missing:
        return _err(f"{name} needs {missing} first")
    try:
        return spec["fn"](case, args)
    except Exception as err:  # noqa: BLE001 - tools report failures, they never raise
        return _err(f"{name} failed: {err}")
