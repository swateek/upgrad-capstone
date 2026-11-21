"""The agent graph, offline: scripted model replies through a mock HTTP transport, a fake corpus,
an in-memory checkpointer. Facts come from the DEV set only. No upgrad call, no model download."""

from __future__ import annotations

import json
from collections import defaultdict

import httpx
import pytest
from conftest import chat_response, mock_openai
from langgraph.checkpoint.memory import InMemorySaver

from customs.agent.graph import CustomsAgent
from customs.llm.chat import ChatClient
from customs.observability.tracing import Tracer
from customs.retrieval.service import RegulationSearch, cites_for
from customs.tools.calc import assess
from customs.tools.models import Line, Profile
from customs.tools.tables import load_tables

MARKERS = {
    "intake": "Extract the traveller's facts",
    "planner": "You plan the calculation",
    "writer": "You write the answer card",
    "review": "You check an answer against its sources",
    "executor": "You run a customs calculation by calling tools",
    "rag": "Use the regulation passages provided",
}

DV01 = {"profile": {"age": 49, "arrived_directly_from": "AT", "exemption_used_last_30_days": False,
                    "trip_hours": 192},
        "basket": [{"abv": 12, "bought_in": "AT", "container_ml": 750, "item": "wine", "origin": "AT",
                    "quantity": 3, "unit": "bottle", "value_usd": 66}]}  # fmt: skip
DV15_T1 = {"profile": {"arrived_directly_from": "IT"},
           "basket": [{"bought_in": "IT", "container_ml": 750, "item": "wine", "origin": "IT",
                       "quantity": 2, "unit": "bottle", "value_usd": 50}]}  # fmt: skip
DV15 = {"profile": {"age": 44, "arrived_directly_from": "IT", "exemption_used_last_30_days": False,
                    "trip_hours": 144}, "basket": DV15_T1["basket"]}  # fmt: skip
DV08 = {"profile": {"age": 36, "arrived_directly_from": "TH", "exemption_used_last_30_days": False,
                    "trip_at_least_48_hours": True},  # the intake's shape (gold: ">=48")
        "basket": [{"bought_in": "TH", "item": "cigarettes", "quantity": 3, "unit": "carton"}]}  # fmt: skip
VAPES = {"profile": {"arrived_directly_from": "CN"},
         "basket": [{"item": "other", "quantity": 5, "other_kind": "vapes_nicotine"}]}  # fmt: skip
WINE_PLAN = {"steps": [{"step": s, "lines": [], "reason": "r"} for s in
             ("check_restrictions", "determine_exemption", "compute_allowance",
              "compute_duty_excise", "search_regulations")]}  # fmt: skip
REVIEW_OK = {"items": [{"index": 1, "supported": True, "reason": "ok"}]}


class Script:
    """Replies per role, in order; records which roles were called."""

    def __init__(self, **queues):
        self.q = defaultdict(list, {k: list(v) for k, v in queues.items()})
        self.seen: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        system = body["messages"][0]["content"]
        role = next(r for r, m in MARKERS.items() if m in system)
        self.seen.append(role)
        if not self.q[role]:
            raise AssertionError(f"no scripted reply left for {role}")
        reply = self.q[role].pop(0)
        if isinstance(reply, dict) and "tool_calls" in reply:
            resp = chat_response("")
            msg = resp["choices"][0]["message"]
            msg["content"] = None
            msg["tool_calls"] = [
                {"id": f"call_{i}", "type": "function",
                 "function": {"name": n, "arguments": json.dumps(a)}}
                for i, (n, a) in enumerate(reply["tool_calls"])
            ]  # fmt: skip
            resp["choices"][0]["finish_reason"] = "tool_calls"
            return httpx.Response(200, json=resp)
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return httpx.Response(200, json=chat_response(text))


class FakeCorpus:
    """Every signed-off clause exists, with a short text; no URLs."""

    def __init__(self, tables):
        ids = {c for r in tables.rules for c in tables.cites(r)}
        ids |= {c for s in tables.states.values() for c in s["cites"]}
        self.docs = {
            c: {"doc_id": c, "citation": f"cite {c}", "text": f"text of {c}", "source_id": c.split(":")[0],
                "topic": "exemptions"}
            for c in ids
        }  # fmt: skip

    def url(self, clause_id):
        return None


def rankings_hit_first_cite(tables):
    """A retriever that finds the rule's first cite at rank 1 (by matching the rule words)."""

    def rankings(queries, filters):
        out = []
        for q in queries:
            hits = []
            for r in tables.rules:
                if tables.rules[r]["name"].replace("_", " ") in q:
                    c = cites_for(tables, r)[0]
                    hits.append({"chunk_id": c, "clause_ids": [c], "n_tokens": 100, "text": f"t {c}",
                                 "citation": c})  # fmt: skip
            out.append(hits)
        return out

    return rankings


@pytest.fixture
def make_agent(settings):
    tables = load_tables()

    def make(script: Script, rankings=None, **overrides):
        s = settings.model_copy(update=overrides)
        chat = ChatClient(s, client=mock_openai(script.handler))
        search = RegulationSearch(
            s,
            rankings=rankings or (lambda qs, fs: [[] for _ in qs]),
            corpus=FakeCorpus(tables),
            tables=tables,
        )
        return CustomsAgent(s, chat=chat, search=search, checkpointer=InMemorySaver(),
                            tracer=Tracer(s), tables=tables)  # fmt: skip

    return make


def handles(facts: dict) -> dict[str, str]:
    """Figure name -> handle, as the card numbers them (same order as the calculators)."""
    from customs.agent.intake import IntakeProfile, to_profile

    profile, _ = to_profile(IntakeProfile.model_validate(facts["profile"]), "")
    a = assess(profile,
               [Line.model_validate(x) for x in facts["basket"]])  # fmt: skip
    return {f.name: f"F{i}" for i, f in enumerate(a.figures, start=1)}


def writer_ok(facts: dict) -> dict:
    h = handles(facts)
    return {"bottom_line": f"You'll owe about [{h['total_owed_usd']}] on the wine.",
            "working": [f"Your trip qualifies for the [{h['exemption_usd']}] exemption [S1].",
                        f"Duty is [{h['duty_total_usd']}] and excise [{h['excise_total_usd']}] [S2]."]}  # fmt: skip


# --- full paths --------------------------------------------------------------------------------


def test_guard_refuses_before_any_model_call(make_agent):
    sc = Script()
    card = make_agent(sc).ask("t1", "What's the best way to hide three cartons in my suitcase?")
    assert card["outcome"] == "refused" and sc.seen == []
    assert card["meta"]["model_calls"] == 0


def test_planner_path_owe_with_handles_rendered(make_agent):
    sc = Script(intake=[DV01], planner=[WINE_PLAN], writer=[writer_ok(DV01)], review=[REVIEW_OK])
    agent = make_agent(sc, rankings=rankings_hit_first_cite(load_tables()))
    card = agent.ask("t1", "Back from 8 days in Vienna ... what do I owe?")
    assert card["outcome"] == "answered" and card["kind"] == "owe"
    assert card["owe_usd"] == "1.45"  # DV01 gold
    assert "$1.45" in card["bottom_line"] and "[F" not in card["bottom_line"]
    assert sc.seen == ["intake", "planner", "writer", "review"]
    m = card["meta"]
    assert m["model_calls"] == 4 and m["plan_source"] == "planner"
    assert m["plan"] == [s["step"] for s in WINE_PLAN["steps"]]
    assert card["citations"] and all(s["retrieved"] for s in card["sources"])
    assert m["retrieval_miss_recovered"] == []
    assert any(r["label"] == "Age" and r["value"] == "49" for r in card["facts_relied_on"])


def test_retrieval_miss_is_recovered_by_clause_id(make_agent):
    sc = Script(intake=[DV01], planner=[WINE_PLAN], writer=[writer_ok(DV01)], review=[REVIEW_OK])
    card = make_agent(sc).ask("t1", "q")  # the retriever finds nothing
    assert card["outcome"] == "answered" and card["citations"]
    assert not any(s["retrieved"] for s in card["sources"])
    assert set(card["meta"]["retrieval_miss_recovered"]) >= {"R9", "R7", "R8"}


def test_clarify_once_then_answer(make_agent):
    h = handles(DV15)
    writer = {"bottom_line": f"You'll owe about [{h['total_owed_usd']}].",
              "working": [f"The [{h['exemption_usd']}] exemption applies [S1]."]}  # fmt: skip
    sc = Script(intake=[DV15_T1, DV15], planner=[WINE_PLAN], writer=[writer], review=[REVIEW_OK])
    agent = make_agent(sc)
    c1 = agent.ask(
        "t2", "Back from Rome with two 750 ml bottles of wine at $25 each. What do I owe?"
    )
    assert c1["outcome"] == "clarify"
    assert {"age_21_plus", "exemption_used_last_30_days"} <= set(c1["clarify_fields"])
    assert c1["meta"]["model_calls"] == 1
    c2 = agent.ask("t2", "I'm 44, I was there 6 days, and I haven't used my exemption this month.")
    assert c2["outcome"] == "answered" and c2["owe_usd"] == "0.64"  # DV15 gold, turn 2
    st = agent.state("t2")
    assert st["asked"] is None and st["answered"] is True


def test_still_missing_hard_fact_after_one_exchange_escalates(make_agent):
    sc = Script(intake=[DV15_T1, DV15_T1])
    agent = make_agent(sc)
    assert agent.ask("t3", "wine from Rome")["outcome"] == "clarify"
    card = agent.ask("t3", "not sure")
    assert card["outcome"] == "escalated" and card["meta"]["escalation"] == "missing_facts"


def test_invalid_plan_twice_falls_back_to_router(make_agent):
    bad = {"steps": [{"step": "compute_allowance", "lines": [], "reason": "r"}]}
    sc = Script(intake=[DV01], planner=[bad, bad], writer=[writer_ok(DV01)], review=[REVIEW_OK])
    card = make_agent(sc).ask("t4", "q")
    assert card["outcome"] == "answered" and card["owe_usd"] == "1.45"
    assert card["meta"]["plan_source"] == "fallback"
    assert sc.seen.count("planner") == 2
    assert any(e["event"] == "plan_fallback" for e in card["meta"]["events"])


def test_router_mode_has_no_planner_call(make_agent):
    sc = Script(intake=[DV01], writer=[writer_ok(DV01)], review=[REVIEW_OK])
    card = make_agent(sc).ask("t5", "q", mode="router")
    assert card["owe_usd"] == "1.45" and "planner" not in sc.seen
    assert card["meta"]["plan_source"] == "router"


def test_writer_typed_number_rewritten_once_then_escalated(make_agent):
    h = handles(DV01)
    typed = {"bottom_line": "You'll owe about $1.45.", "working": ["Duty applies [S1]."]}
    sc = Script(intake=[DV01, DV01], planner=[WINE_PLAN], writer=[typed, writer_ok(DV01), typed, typed],
                review=[REVIEW_OK])  # fmt: skip
    agent = make_agent(sc)
    ok = agent.ask("t6", "q")
    assert ok["outcome"] == "answered" and sc.seen.count("writer") == 2
    assert any(e["event"] == "verifier_failed" for e in ok["meta"]["events"])
    bad = agent.ask("t6", "same again please")  # plan reused; writer fails twice
    assert bad["outcome"] == "escalated" and bad["meta"]["escalation"] == "verifier_failed"
    assert h["total_owed_usd"]


def test_correction_reuses_plan_and_recomputes(make_agent):
    corrected = json.loads(json.dumps(DV01))
    corrected["basket"][0]["quantity"] = 4
    sc = Script(intake=[DV01, corrected], planner=[WINE_PLAN],
                writer=[writer_ok(DV01), writer_ok(corrected)], review=[REVIEW_OK, REVIEW_OK])  # fmt: skip
    agent = make_agent(sc)
    first = agent.ask("t7", "q")
    second = agent.ask("t7", "Wait, it's four bottles.")
    assert sc.seen.count("planner") == 1  # replan not needed: the plan is still valid
    assert second["meta"]["plan_source"] == "reused"
    assert first["owe_usd"] != second["owe_usd"]
    ev = next(e for e in second["meta"]["events"] if e["event"] == "facts_changed")
    assert ev["fields"] == ["line 1"] and "compute_duty_excise" in ev["stale"]


def test_budget_exceeded_escalates(make_agent):
    sc = Script(intake=[DV01], planner=[WINE_PLAN])
    card = make_agent(sc, agent_step_limit=1).ask("t8", "q")
    assert card["outcome"] == "escalated" and card["meta"]["escalation"] == "budget"


def test_vapes_out_of_scope_after_intake(make_agent):
    sc = Script(intake=[VAPES])
    card = make_agent(sc).ask("t9", "five vape pens from Shenzhen")
    assert card["outcome"] == "out_of_scope"
    assert card["notes"][0]["id"] == "scope_note:vapes_nicotine"


def test_tobacco_only_plan_may_skip_duty(make_agent):
    plan = {"steps": [{"step": s, "lines": [], "reason": "r"} for s in
            ("check_restrictions", "determine_exemption", "compute_allowance", "search_regulations")]}  # fmt: skip
    h = handles(DV08)
    writer = {"bottom_line": "The cigarettes over the allowance may be seized; declare them.",
              "working": [f"[{h['excess_sticks_1']}] are over the allowance [S1]."]}  # fmt: skip
    sc = Script(intake=[DV08], planner=[plan], writer=[writer], review=[REVIEW_OK])
    card = make_agent(sc).ask("t10", "three cartons from Thailand")
    assert card["kind"] == "seizure_risk" and card["meta"]["plan_source"] == "planner"
    assert any(n["id"] == "seizure_risk" for n in card["notes"])


def test_calculator_escalation_skips_writer(make_agent):
    big = json.loads(json.dumps(DV01))
    big["basket"][0]["value_usd"] = 950
    sc = Script(intake=[big], planner=[WINE_PLAN])
    card = make_agent(sc).ask("t11", "q")
    assert card["outcome"] == "escalated" and card["meta"]["escalation"] == "basket_over_800"
    assert "writer" not in sc.seen and card["handoff"]["facts_relied_on"]["age"] == 49


def test_single_rag_mode_one_call(make_agent):
    ans = {"outcome": "answered", "kind": "owe", "owe_usd": 2.5, "clarify_question": None,
           "citations": ["cfr19_p148:148.33(d)"], "answer": "About $2.50."}  # fmt: skip
    hits = [[{"chunk_id": "x", "clause_ids": ["cfr19_p148:148.33(d)"], "citation": "19 CFR 148.33",
              "n_tokens": 50, "text": "One liter..."}]]  # fmt: skip
    sc = Script(rag=[ans])
    card = make_agent(sc, rankings=lambda qs, fs: hits).ask("t12", "q", mode="single_rag")
    assert sc.seen == ["rag"] and card["owe_usd"] == "2.50"
    assert card["citations"] == ["cfr19_p148:148.33(d)"] and card["meta"]["tool_calls"] == 1


def test_tool_calling_mode_measures_transcription(make_agent):
    line = {"line": 1, "item": "wine", "quantity": 3, "unit": "bottle", "container_ml": 750,
            "abv": 12, "value_usd": 60, "origin": "AT"}  # value mistyped: 66 -> 60  # fmt: skip
    calls = {"tool_calls": [
        ("check_restrictions", {"lines": [{"line": 1, "item": "wine", "origin": "AT"}]}),
        ("determine_exemption", {"trip_hours": 192, "arrived_directly_from": "AT",
                                 "exemption_used_last_30_days": False}),
        ("compute_allowance", {"age": 49, "lines": [line]}),
        ("compute_duty_excise", {"lines": [{"line": 1, "value_usd": 60, "abv": 12, "origin": "AT"}]}),
        ("search_regulations", {}),
    ]}  # fmt: skip
    mistyped = json.loads(json.dumps(DV01))
    mistyped["basket"][0]["value_usd"] = 60
    sc = Script(intake=[DV01], planner=[WINE_PLAN], executor=[calls, "DONE"],
                writer=[writer_ok(mistyped)], review=[REVIEW_OK])  # fmt: skip
    card = make_agent(sc).ask("t13", "q", mode="tool_calling")
    assert card["outcome"] == "answered"
    assert card["owe_usd"] != "1.45"  # the mistyped value changed the answer, as measured
    tc = next(e for e in card["meta"]["events"] if e["event"] == "tool_calling")
    assert tc["transcription_diffs"] == 1 and tc["diff_fields"] == ["line 1.value_usd"]
    assert card["meta"]["tool_calls"] == 6  # 5 by the model + citations


def test_tool_calling_blocks_repeats_and_bad_args(make_agent):
    calls = {"tool_calls": [
        ("check_restrictions", {"lines": [{"line": 1, "item": "wine"}]}),
        ("check_restrictions", {"lines": [{"line": 1, "item": "wine"}]}),
        ("determine_exemption", {"trip_hours": "a week"}),
    ]}  # fmt: skip
    sc = Script(intake=[DV01], planner=[WINE_PLAN], executor=[calls, "DONE"])
    sc.q["planner"].append(WINE_PLAN)  # replan after the audit failure
    sc.q["executor"] += ["DONE"]
    card = make_agent(sc).ask("t14", "q", mode="tool_calling")
    assert card["outcome"] == "escalated"
    tc = next(e for e in card["meta"]["events"] if e["event"] == "tool_calling")
    assert tc["repeated_blocked"] == 1 and tc["bad_arguments"] == 1


def test_finalise_survives_skipped_steps():
    """A model executor may skip steps; finalising must report, not crash (the audit decides)."""
    from customs.agent.executor import audit, finalise
    from customs.tools.calc import new_case, step_normalise, step_restrictions

    for facts in (DV01, DV15):
        case = new_case(Profile.model_validate(facts["profile"]),
                        [Line.model_validate(x) for x in facts["basket"]])  # fmt: skip
        step_normalise(case)
        step_restrictions(case)
        a = finalise(case)
        assert a.figures == []
        assert "determine_exemption did not run" in audit(case, [], a)


DOCS = __import__("customs.config", fromlist=["PROJECT_ROOT"]).PROJECT_ROOT / "data" / "chunks"


@pytest.mark.skipif(not (DOCS / "documents.jsonl").exists(), reason="corpus not built (CI)")
def test_oracle_dev_is_perfect():
    """With perfect model replies, every dev turn is correct: the non-model pipeline's ceiling."""
    from eval.oracle_dev import run

    right, total = run(verbose=False)
    assert (right, total) == (23, 23)


def test_prohibited_only_is_templated_without_writer(make_agent):
    cuban = {"profile": {"age": 50, "trip_hours": 120, "arrived_directly_from": "CA",
                         "exemption_used_last_30_days": False},
             "basket": [{"item": "spirits", "quantity": 1, "unit": "bottle", "origin": "CU",
                         "bought_in": "CA"}]}  # fmt: skip
    sc = Script(intake=[cuban], planner=[{"steps": [
        {"step": "check_restrictions", "lines": [], "reason": ""},
        {"step": "search_regulations", "lines": [], "reason": ""}]}])  # fmt: skip
    card = make_agent(sc).ask("t15", "Havana Club made in Cuba, bought in Toronto. OK?")
    assert card["kind"] == "prohibited" and card["bottom_line"].startswith("No:")
    assert "writer" not in sc.seen and "(cite " in card["bottom_line"]
