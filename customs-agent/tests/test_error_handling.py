"""Error handling (Days 8-9 exit criterion; CLAUDE.md "Error handling"): one test per failure
the agent must survive. Scripted model, fake search: no network.

  JSON          malformed -> 2 repairs with the error fed back -> escalate
  endpoint      the model call raises -> escalated, error recorded, never an exception
  search        retrieval raises -> the same
  ToolError     missing fact -> clarify; rule -> escalate; out of scope -> scope note;
                unreadable unit -> ask the size; other tool / plan error -> back to the planner,
                then the code router's plan, then escalate
  loops         a repeated tool is rejected by the validator
  caps          10 tool steps and 12,000 tokens per question
  verifier      fails twice -> escalate
  tracing       a tracer failure never loses the answer
  sessions      a failed turn is recorded, the conversation keeps its facts
"""

from __future__ import annotations

import pytest

from src.agent import pipeline
from src.agent.pipeline import MAX_TOOL_STEPS, answer_question
from src.agent.planner import validate
from src.agent.router import ROUTER_PLAN
from tests.test_agent import DEV, GOOD_D01, ScriptedLLM, fake_search, intake_for
from tests.test_planner import PLAN_NO_STATE, facts

OK = {"advises_evasion": False}


def wine_intake(**line):
    base = intake_for("D01")
    base["basket"][0].update(line)
    return base


# ------------------------------------------------------------------ JSON


def test_malformed_json_twice_is_repaired() -> None:
    llm = ScriptedLLM(
        intake=["not json", '{"request_kind": "assess"', intake_for("D01")],
        writer=[GOOD_D01],
        verifier=[OK],
    )
    run = answer_question(DEV["D01"]["question"], llm=llm, search=fake_search)
    assert run.answer.outcome == "answered" and llm.calls[:3] == [
        "intake",
        "intake_repair",
        "intake_repair",
    ]


def test_malformed_json_three_times_escalates() -> None:
    llm = ScriptedLLM(intake=["not json"])
    run = answer_question(DEV["D01"]["question"], llm=llm, search=fake_search)
    assert (
        run.answer.outcome == "escalated"
        and run.reason == "intake_failed"
        and len(llm.calls) == 3
    )


# ------------------------------------------------------------------ endpoint and search


def test_endpoint_failure_is_an_escalation_not_a_crash() -> None:
    class Down:
        def chat(self, *a, **k):
            raise ConnectionError("endpoint unreachable")

    run = answer_question(DEV["D01"]["question"], llm=Down(), search=fake_search)
    assert run.answer.outcome == "escalated" and "ConnectionError" in run.error


def test_search_failure_is_an_escalation_not_a_crash() -> None:
    def broken(args):
        raise TimeoutError("index unavailable")

    llm = ScriptedLLM(intake=[intake_for("D01")])
    run = answer_question(DEV["D01"]["question"], llm=llm, search=broken)
    assert run.answer.outcome == "escalated" and "TimeoutError" in run.error


# ------------------------------------------------------------------ tool errors


def test_tool_missing_fact_asks() -> None:
    llm = ScriptedLLM(intake=[wine_intake(size=None)])
    run = answer_question(
        "4 bottles of wine after 10 days in Italy, 13%, $30 each. I'm 34, first trip this year.",
        llm=llm,
        search=fake_search,
    )
    assert run.answer.outcome == "clarify" and "size" in run.answer.clarify_facts


def test_tool_out_of_scope_gives_the_scope_note() -> None:
    f = intake_for("D01")
    f["profile"]["direct_arrival_from"] = "VI"
    llm = ScriptedLLM(intake=[f])
    run = answer_question(
        "Direct from the Virgin Islands: 4 bottles of wine, 750 ml, 13%, $30 each. I'm 34, 10 days, first trip this year.",
        llm=llm,
        search=fake_search,
    )
    assert (
        run.answer.outcome == "refused"
        and run.reason == "out_of_scope_insular_possession_arrivals"
    )


def test_unreadable_unit_asks_for_the_size() -> None:
    llm = ScriptedLLM(intake=[wine_intake(size={"value": 1, "unit": "jug"})])
    run = answer_question(
        "4 jugs of wine after 10 days in Italy, 13%, $30 each. I'm 34, first trip this year.",
        llm=llm,
        search=fake_search,
    )
    assert run.answer.outcome == "clarify" and run.answer.clarify_facts == ["size"]


def test_rule_escalation_stands() -> None:
    f = intake_for("D01")
    f["basket"][0].update(item="Russian vodka", type="spirits", origin="RU", abv=40)
    llm = ScriptedLLM(intake=[f])
    run = answer_question(
        "4 bottles of Russian vodka, 750 ml, 40%, $30 each, 10 days in Latvia, I'm 34, first trip this year.",
        llm=llm,
        search=fake_search,
    )
    assert run.answer.outcome == "escalated" and run.reason == "russian_origin_alcohol"


def _flaky_execute(fail_times: int):
    """execute() that reports a tool error for its first `fail_times` calls."""
    real = pipeline.execute
    state = {"n": 0}

    def fake(*a, **k):
        r = real(*a, **k)
        if state["n"] < fail_times:
            state["n"] += 1
            r.outcome, r.rule_id, r.message = (
                "escalated",
                "invalid_input",
                "compute_allowance: no rule matches line 1",
            )
            r.error = {"kind": "tool_error", "message": r.message}
        return r

    return fake


def test_tool_error_goes_back_to_the_planner(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "execute", _flaky_execute(1))
    seen = []

    class Spy(ScriptedLLM):
        def chat(self, messages, *, stage, **kw):
            if stage.startswith("planner"):
                seen.append(messages[-1]["content"])
            return super().chat(messages, stage=stage, **kw)

    other = [
        "normalise_units",
        "check_restrictions",
        "determine_exemption",
        "compute_allowance",
        "compute_duty_excise",
        "lookup_state_rule",
        "search_regulations",
    ]
    llm = Spy(
        intake=[intake_for("D01")],
        planner=[
            {"steps": PLAN_NO_STATE, "reason": "x"},
            {"steps": other, "reason": "y"},
        ],
        writer=[GOOD_D01],
        verifier=[OK],
    )
    run = answer_question(
        DEV["D01"]["question"], llm=llm, search=fake_search, mode="planner"
    )
    assert any("Running your plan failed" in m for m in seen)
    assert run.answer.outcome == "answered" and any(
        t.get("step") == "tool_error" for t in run.trace
    )


def test_tool_error_that_persists_falls_back_to_the_router_then_escalates(
    monkeypatch,
) -> None:
    monkeypatch.setattr(pipeline, "execute", _flaky_execute(99))
    llm = ScriptedLLM(
        intake=[intake_for("D01")], planner=[{"steps": PLAN_NO_STATE, "reason": "x"}]
    )
    run = answer_question(
        DEV["D01"]["question"], llm=llm, search=fake_search, mode="planner"
    )
    assert run.answer.outcome == "escalated" and run.plan_fallback is True
    assert any(t.get("step") == "tool_error_router" for t in run.trace)


# ------------------------------------------------------------------ loops and caps


def test_repeated_tool_calls_are_blocked() -> None:
    assert any(
        "at most once" in e
        for e in validate(
            [*ROUTER_PLAN[:-1], "compute_duty_excise", "search_regulations"], facts()
        )
    )


def test_tool_step_cap(monkeypatch) -> None:
    real = pipeline.route

    def long_route(*a, **k):
        r = real(*a, **k)
        r.tool_steps = MAX_TOOL_STEPS  # + search = 11
        return r

    monkeypatch.setattr(pipeline, "route", long_route)
    llm = ScriptedLLM(intake=[intake_for("D01")])
    run = answer_question(DEV["D01"]["question"], llm=llm, search=fake_search)
    assert run.answer.outcome == "escalated" and run.reason == "budget_exceeded"


# ------------------------------------------------------------------ verifier, tracing, sessions


def test_verifier_failing_twice_escalates() -> None:
    bad = {
        **GOOD_D01,
        "explanation": "You owe $9.99 in duty.",
    }  # bottom line is code (v2)
    llm = ScriptedLLM(intake=[intake_for("D01")], writer=[bad, bad], verifier=[OK])
    run = answer_question(DEV["D01"]["question"], llm=llm, search=fake_search)
    assert run.answer.outcome == "escalated" and run.reason == "verifier_failed"


def test_tracer_failure_keeps_the_answer(tmp_path) -> None:
    from fastapi.testclient import TestClient

    from app.api import Service, create_app
    from src.agent.session import Sessions

    class BrokenTracer:
        def record(self, *a, **k):
            raise RuntimeError("langfuse down")

    llm = ScriptedLLM(intake=[intake_for("D01")], writer=[GOOD_D01], verifier=[OK])
    c = TestClient(
        create_app(
            Service(
                llm,
                fake_search,
                BrokenTracer(),
                [],
                Sessions(llm, fake_search, db=tmp_path / "s.db"),
            )
        )
    )
    body = c.post(
        "/api/ask", json={"question": DEV["D01"]["question"], "mode": "router"}
    ).json()
    assert body["outcome"] == "answered" and body["trace"]["error"] == "RuntimeError"


@pytest.mark.parametrize("exc", [ConnectionError, TimeoutError, ValueError])
def test_session_turn_failure_is_recorded(tmp_path, exc) -> None:
    from src.agent.session import Sessions

    class Flaky(ScriptedLLM):
        def chat(self, messages, *, stage, **kw):
            if stage == "turn_intake":
                raise exc("boom")
            return super().chat(messages, stage=stage, **kw)

    llm = Flaky(intake=[intake_for("D01")], writer=[GOOD_D01], verifier=[OK])
    s = Sessions(llm, fake_search, db=tmp_path / "s.db")
    s.turn("c", message=DEV["D01"]["question"])
    r = s.turn("c", message="actually 3 bottles")
    assert r.answer.outcome == "escalated" and exc.__name__ in (r.error or "")
    assert s.state("c")["basket"][0]["quantity"]["value"] == 4
