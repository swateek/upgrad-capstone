"""`tool_calling` mode (plan §4.3, D19): the executor is the model, calling the tools natively.

The planner and validator run as in `planner` mode. Here the model must call the plan's tools
itself and TYPE the facts each one needs into its arguments (quantities, values, ages, origins):
that transcription is what this mode measures against the code executor. Arguments are checked
with Pydantic (one retry per tool on bad arguments); a repeated identical call is blocked
(the reference's ToolArgGuard). The facts the model typed are applied before the calculator runs,
so a mistyped value changes the result exactly as it would in production; the differences from
the intake's facts are recorded as `transcription_diffs`.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from customs.agent.context import current
from customs.agent.planner import Plan
from customs.config import PROJECT_ROOT
from customs.llm.chat import ChatClient
from customs.tools.calc import (
    Case,
    new_case,
    step_allowance,
    step_duty_excise,
    step_exemption,
    step_normalise,
    step_restrictions,
)
from customs.tools.models import Line, Profile
from customs.tools.registry import run_tool
from customs.tools.tables import Tables

PROMPT = PROJECT_ROOT / "pack" / "prompts" / "tool_executor.md"
MAX_TOKENS = 500


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RestrictionLine(_Args):
    line: int
    item: str
    origin: str | None = None
    bought_in: str | None = None
    brand: str | None = None


class CalcLine(_Args):
    line: int
    item: str
    quantity: float | None = None
    unit: str | None = None
    container_ml: float | None = None
    abv: float | None = None
    value_usd: float | None = None
    origin: str | None = None


class DutyLine(_Args):
    line: int
    value_usd: float | None = None
    abv: float | None = None
    origin: str | None = None


class CheckRestrictions(_Args):
    lines: list[RestrictionLine] = Field(min_length=1)


class DetermineExemption(_Args):
    trip_hours: float | None = None
    arrived_directly_from: str | None = None
    exemption_used_last_30_days: bool | None = None


class ComputeAllowance(_Args):
    age: int | None = None
    lines: list[CalcLine] = Field(min_length=1)


class ComputeDutyExcise(_Args):
    lines: list[DutyLine] = Field(min_length=1)


class LookupStateRule(_Args):
    state: str | None = None


class SearchRegulations(_Args):
    pass


ARGS: dict[str, type[_Args]] = {
    "check_restrictions": CheckRestrictions,
    "determine_exemption": DetermineExemption,
    "compute_allowance": ComputeAllowance,
    "compute_duty_excise": ComputeDutyExcise,
    "lookup_state_rule": LookupStateRule,
    "search_regulations": SearchRegulations,
}
DESCRIPTIONS = {
    "check_restrictions": "Cuban origin, ambiguous brands, Russian alcohol, other goods. Give every basket line.",
    "determine_exemption": "The $800 or $200 exemption from the trip facts.",
    "compute_allowance": "Duty-free vs over-the-allowance amounts. Give the traveller's age and every allowed line.",
    "compute_duty_excise": "Duty and federal excise on alcohol over the allowance. Give the alcohol lines.",
    "lookup_state_rule": "The arrival state's alcohol flag.",
    "search_regulations": "Find the regulations behind the answer (the query is built for you).",
}  # fmt: skip
STEP_DONE = {"determine_exemption": "exemption", "compute_allowance": "allowance",
             "compute_duty_excise": "duty"}  # fmt: skip


def tool_specs() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": DESCRIPTIONS[name],
                "parameters": model.model_json_schema(),
            },
        }
        for name, model in ARGS.items()
    ]


class ModelFacts:
    """The facts as the model has typed them so far (starting from the intake's)."""

    def __init__(self, profile: Profile, basket: list[Line]) -> None:
        self.profile = profile.model_copy(deep=True)
        self.basket = [ln.model_copy(deep=True) for ln in basket]

    def apply(self, name: str, args: _Args) -> None:
        """Only fields the model actually typed (exclude_unset); validated like the intake's."""
        upd = args.model_dump(exclude={"lines"}, exclude_unset=True)
        if "state" in upd:
            upd["arrival_state"] = upd.pop("state")
        if upd:
            self.profile = Profile.model_validate(self.profile.model_dump() | upd)
        for ln in getattr(args, "lines", []) or []:
            i = ln.line - 1
            if 0 <= i < len(self.basket):
                typed = ln.model_dump(exclude={"line"}, exclude_unset=True)
                self.basket[i] = Line.model_validate(self.basket[i].model_dump() | typed)

    def case(self, tables: Tables, done: list[str]) -> Case:
        c = new_case(self.profile, self.basket, tables)
        step_normalise(c)
        step_restrictions(c)
        for step, fn in (("exemption", step_exemption), ("allowance", step_allowance),
                         ("duty", step_duty_excise)):  # fmt: skip
            if step in done:
                fn(c)
        return c


def diffs(a: dict, b: dict, prefix: str = "") -> list[str]:
    out = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            out.append(f"{prefix}{k}")
    return out


def execute_tool_calling(
    chat: ChatClient, plan: Plan, profile: Profile, basket: list[Line], tables: Tables
) -> tuple[Case, list[dict], dict[str, Any]]:
    ctx = current()
    facts = ModelFacts(profile, basket)
    done: list[str] = []
    results: list[dict] = []
    stats: Counter = Counter()
    seen: set[tuple[str, str]] = set()
    bad: Counter = Counter()
    facts_json = json.dumps(
        {"profile": profile.model_dump(exclude_defaults=True),
         "basket": [{"line": i, **ln.model_dump(exclude_none=True)} for i, ln in enumerate(basket, 1)]},
        separators=(",", ":"),
    )  # fmt: skip
    plan_txt = ", ".join(s.step for s in plan.steps)
    msgs: list[dict[str, Any]] = [
        {"role": "system", "content": PROMPT.read_text(encoding="utf-8").strip()},
        {"role": "user", "content": f"Facts: {facts_json}\n\nPlan: {plan_txt}"},
    ]
    specs = tool_specs()
    case = facts.case(tables, done)
    for _ in range(len(plan.steps) + 2):  # rounds
        ctx.before_model_call()
        res = chat.complete(msgs, max_tokens=MAX_TOKENS, tools=specs, tool_choice="auto",
                            name="executor")  # fmt: skip
        ctx.after_model_call("executor", res)
        calls = list(getattr(res.message, "tool_calls", None) or [])
        if not calls:
            break
        msgs.append(
            {
                "role": "assistant",
                "content": res.message.content or "",
                "tool_calls": [
                    {"id": c.id, "type": "function",
                     "function": {"name": c.function.name, "arguments": c.function.arguments}}
                    for c in calls
                ],
            }
        )  # fmt: skip
        for c in calls:
            out = _one_call(c.function.name, c.function.arguments, facts, done, tables, seen, bad,
                            stats)  # fmt: skip
            if "case" in out:
                case = out.pop("case")
            results.append({"step": c.function.name, "lines": [], "result": out})
            ctx.tool_call(c.function.name, out)
            msgs.append({"role": "tool", "tool_call_id": c.id,
                         "content": json.dumps(out, default=str)[:1500]})  # fmt: skip
    truth = {"profile": profile.model_dump(), "basket": [ln.model_dump() for ln in basket]}
    typed = {
        "profile": facts.profile.model_dump(),
        "basket": [ln.model_dump() for ln in facts.basket],
    }
    td = diffs(truth["profile"], typed["profile"], "profile.")
    for i, (a, b) in enumerate(zip(truth["basket"], typed["basket"], strict=False), start=1):
        td += diffs(a, b, f"line {i}.")
    stats["transcription_diffs"] = len(td)
    return case, results, {**dict(stats), "diff_fields": td, "steps_run": done}


def _one_call(
    name: str,
    raw: str,
    facts: ModelFacts,
    done: list[str],
    tables: Tables,
    seen: set,
    bad: Counter,
    stats: Counter,
) -> dict:
    if name not in ARGS:
        stats["unknown_tool"] += 1
        return {"error": f"unknown tool {name}", "retryable": False}
    key = (name, raw)
    if key in seen:
        stats["repeated_blocked"] += 1
        return {"error": "repeated call blocked: this exact call already ran", "retryable": False}
    seen.add(key)
    try:
        args = ARGS[name].model_validate(json.loads(raw or "{}"))
    except (json.JSONDecodeError, ValidationError) as err:
        stats["bad_arguments"] += 1
        bad[name] += 1
        if bad[name] > 1:
            return {"error": f"invalid arguments again for {name}; giving up", "retryable": False}
        return {"error": f"invalid arguments: {str(err)[:300]}", "retryable": True}
    if name == "search_regulations":
        return {"ok": True, "note": "sources are attached to the answer"}
    try:
        facts.apply(name, args)
    except ValidationError as err:
        stats["bad_arguments"] += 1
        return {"error": f"invalid values: {str(err)[:300]}", "retryable": True}
    case = facts.case(tables, done)
    lines = [ln.line for ln in getattr(args, "lines", [])] if name != "check_restrictions" else []
    reg_args = {"lines": lines} if name in ("check_restrictions", "compute_allowance",
                                            "compute_duty_excise") else {}  # fmt: skip
    out = run_tool(case, name, reg_args)
    if "error" in out:
        stats["tool_errors"] += 1
    elif name in STEP_DONE and STEP_DONE[name] not in done:
        done.append(STEP_DONE[name])
    out["case"] = case
    return out
