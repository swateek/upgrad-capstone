"""LLM planner path: validator rules, repair, fallback to the router plan, and the hard budget."""

from __future__ import annotations

import pytest

from src.agent.intake import IntakeResult
from src.agent.pipeline import MAX_TOKENS, answer_question
from src.agent.planner import describe, validate
from src.agent.router import ROUTER_PLAN, ROUTER_WHATIF_PLAN, execute, route
from tests._chain import line_from_fact, profile_from_fact
from tests.test_agent import (
    DEV,
    GOOD_D01,
    ROUTABLE,
    ScriptedLLM,
    fake_search,
    intake_for,
)


def facts(item_id="D01", **upd) -> IntakeResult:
    r = IntakeResult.model_validate(intake_for(item_id))
    return r.model_copy(update=upd) if upd else r


def test_router_plans_are_valid() -> None:
    assert validate(ROUTER_PLAN, facts()) == []
    whatif = facts(owe_less_than_usd=5.0)
    assert validate(ROUTER_WHATIF_PLAN, whatif) == []


@pytest.mark.parametrize(
    "steps,needle",
    [
        ([], "empty"),
        (
            [
                "normalise_units",
                "determine_exemption",
                "check_restrictions",
                "compute_allowance",
                "compute_duty_excise",
                "search_regulations",
            ],
            "order",
        ),
        (
            [
                "normalise_units",
                "check_restrictions",
                "determine_exemption",
                "compute_allowance",
                "search_regulations",
            ],
            "missing steps",
        ),
        (
            [
                "normalise_units",
                "check_restrictions",
                "determine_exemption",
                "compute_allowance",
                "compute_duty_excise",
            ],
            "last",
        ),
        (
            [*ROUTER_PLAN[:-1], "search_regulations", "search_regulations"],
            "at most once",
        ),
        (["whatif_optimise", *ROUTER_PLAN], "only for a what-if"),
        (
            ["normalise_units", "escalate_to_human", "search_regulations"],
            "after check_restrictions",
        ),
        (["made_up_tool", *ROUTER_PLAN], "unknown"),
    ],
)
def test_validator_rejects_bad_plans(steps, needle) -> None:
    assert any(needle in e for e in validate(steps, facts()))


def test_state_rule_required_only_with_an_arrival_state() -> None:
    nj = facts(profile=facts().profile.model_copy(update={"arrival_state": "NJ"}))
    no_state = [s for s in ROUTER_PLAN if s != "lookup_state_rule"]
    assert any("include lookup_state_rule" in e for e in validate(no_state, nj))
    assert validate(no_state, facts()) == []
    assert validate(ROUTER_PLAN, facts()) == []  # harmless without a state


@pytest.mark.parametrize("item_id", ROUTABLE)
def test_executor_with_the_router_plan_is_the_router(item_id) -> None:
    d = DEV[item_id]
    p = profile_from_fact(d["facts"]["profile"])
    b = [line_from_fact(f) for f in d["facts"]["basket"]]
    a, r = execute(p, b, ROUTER_PLAN), route(p, b)
    assert (a.outcome, a.line_types, a.missing, a.citations) == (
        r.outcome,
        r.line_types,
        r.missing,
        r.citations,
    )


def test_describe_lists_the_facts_not_the_numbers_to_compute() -> None:
    text = describe(facts())
    assert "age: 34" in text and "item 1" in text and "$" not in text


PLAN_NO_STATE = [s for s in ROUTER_PLAN if s != "lookup_state_rule"]


def test_planner_valid_plan_end_to_end() -> None:
    llm = ScriptedLLM(
        intake=[intake_for("D01")],
        planner=[{"steps": PLAN_NO_STATE, "reason": "standard assessment"}],
        writer=[GOOD_D01],
        verifier=[{"advises_evasion": False}],
    )
    run = answer_question(
        DEV["D01"]["question"], llm=llm, search=fake_search, mode="planner"
    )
    assert run.answer.outcome == "answered" and run.answer.total_usd == 2.97
    assert run.plan_fallback is False and run.tool_steps == len(PLAN_NO_STATE)
    assert llm.calls == ["intake", "planner", "writer", "verifier"]


def test_invalid_plan_is_repaired_once() -> None:
    bad = {
        "steps": ["normalise_units", "compute_duty_excise", "search_regulations"],
        "reason": "x",
    }
    llm = ScriptedLLM(
        intake=[intake_for("D01")],
        planner=[bad, {"steps": PLAN_NO_STATE, "reason": "fixed"}],
        writer=[GOOD_D01],
        verifier=[{"advises_evasion": False}],
    )
    run = answer_question(
        DEV["D01"]["question"], llm=llm, search=fake_search, mode="planner"
    )
    assert run.plan_fallback is False and llm.calls.count("planner") == 2
    assert run.answer.total_usd == 2.97


def test_twice_invalid_plan_falls_back_to_the_router() -> None:
    bad = {"steps": ["compute_duty_excise", "search_regulations"], "reason": "x"}
    llm = ScriptedLLM(
        intake=[intake_for("D01")],
        planner=[bad, bad],
        writer=[GOOD_D01],
        verifier=[{"advises_evasion": False}],
    )
    run = answer_question(
        DEV["D01"]["question"], llm=llm, search=fake_search, mode="planner"
    )
    assert run.plan_fallback is True and run.answer.total_usd == 2.97
    assert any(t.get("fallback") for t in run.trace)


def test_planner_on_the_whatif_question() -> None:
    f = DEV["D12"]["facts"]
    w = f["whatif"]
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {k: v for k, v in f["profile"].items() if v is not None},
                "basket": [
                    {
                        "item": w["item"],
                        "category": "alcohol",
                        "type": "wine",
                        "quantity": None,
                        "size": {"value": w["unit_ml"], "unit": "ml"},
                        "abv": w["abv"],
                        "unit_price_usd": w["unit_price_usd"],
                        "origin": w.get("origin"),
                    }
                ],
                "owe_less_than_usd": 5,
            }
        ],
        planner=[{"steps": ["whatif_optimise", *PLAN_NO_STATE], "reason": "what-if"}],
        writer=[
            {
                "bottom_line": "Up to 7 bottles owe $4.59.",
                "explanation": "Declare them.",
                "sources": [1],
            }
        ],
        verifier=[{"advises_evasion": False}],
    )
    run = answer_question(
        DEV["D12"]["question"], llm=llm, search=fake_search, mode="planner"
    )
    assert run.plan_fallback is False
    assert run.answer.whatif.max_units == DEV["D12"]["gold"]["whatif"]["max_units"]


def test_token_budget_escalates() -> None:
    class Hungry(ScriptedLLM):
        def chat(self, messages, *, stage, **kw):
            r = super().chat(messages, stage=stage, **kw)
            r.usage.total_tokens = MAX_TOKENS  # one call uses the whole budget
            return r

    llm = Hungry(
        intake=[intake_for("D01")],
        planner=[{"steps": PLAN_NO_STATE, "reason": "x"}],
        writer=[GOOD_D01],
        verifier=[{"advises_evasion": False}],
    )
    # intake uses the whole budget and the planner goes over it: stop before the writer
    run = answer_question(
        DEV["D01"]["question"], llm=llm, search=fake_search, mode="planner"
    )
    assert run.answer.outcome == "escalated" and run.reason == "budget_exceeded"
    assert "writer" not in llm.calls
    assert "writer" not in llm.calls
