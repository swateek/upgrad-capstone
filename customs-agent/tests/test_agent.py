"""Agent v0 (code router) with a scripted model and a fake search: no network, no model download."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agent.intake import IntakeResult
from src.agent.pipeline import answer_question
from src.agent.router import route
from src.agent.verifier import numbers, verify
from src.agent.writer import WriterOut
from src.safety.guard import check_question, sanitise_clause
from src.schemas import Clause, Clauses
from tests._chain import line_from_fact, profile_from_fact

ROOT = Path(__file__).parents[1]
DEV = {
    d["id"]: d
    for d in (
        json.loads(x)
        for x in (ROOT / "eval" / "dev_set.jsonl").read_text().splitlines()
    )
}


# ------------------------------------------------------------------ fakes


class ScriptedLLM:
    """Returns scripted JSON per stage, in order; records every call."""

    def __init__(self, **by_stage):
        self.by_stage = {k: list(v) for k, v in by_stage.items()}
        self.calls: list[str] = []

    def chat(self, messages, *, stage, **kw):
        self.calls.append(stage)
        base = stage.removesuffix("_repair")
        queue = self.by_stage.get(base)
        if not queue:
            raise AssertionError(f"unexpected call: {stage}")
        content = queue.pop(0) if len(queue) > 1 else queue[0]
        if not isinstance(content, str):
            content = json.dumps(content)
        return SimpleNamespace(content=content, usage=SimpleNamespace(total_tokens=100))


def fake_search(args):
    """Every requested id is 'retrieved', plus one search hit."""
    clauses = [
        Clause(
            citation_id=c,
            chunk_id=f"{c}#01",
            heading=c,
            text=f"Text of {c}. Returning residents: 1 liter of alcoholic beverages; 48 hours.",
            authority="primary_regulation",
            as_of="2026-11-19",
            found_by="citation_id",
        )
        for c in args.citation_ids[: args.k]
    ]
    clauses.append(
        Clause(
            citation_id="cbp-duty-info",
            chunk_id="cbp-duty-info#03",
            heading="Customs Duty Information",
            text="Declare all alcohol.",
            authority="agency_guidance",
            as_of="2026-11-21",
            found_by="search",
            rank=1,
        )
    )
    return Clauses(
        query=args.query,
        clauses=clauses,
        retrieved_ids=[c.citation_id for c in clauses],
        method="fake",
    )


def intake_for(item_id: str, **extra) -> dict:
    f = DEV[item_id]["facts"]
    basket = []
    for b in f["basket"]:
        ln = line_from_fact(b).model_dump(mode="json", exclude_none=True)
        basket.append(ln)
    p = {k: v for k, v in f["profile"].items() if v is not None}
    if "trip" in p:
        p["trip"] = p["trip"]
    return {"request_kind": "assess", "profile": p, "basket": basket, **extra}


GOOD_D01 = {
    "bottom_line": "You owe $2.97 on the wine.",
    "explanation": "Your $800 exemption covers 1 liter of alcohol. The other 2 L are dutiable: 3% duty of $2.40 plus $0.57 federal excise. Declare it at the border.",
    "sources": [1, 3],
}


# ------------------------------------------------------------------ guard


@pytest.mark.parametrize(
    "item_id,reason",
    [
        ("D16", "out_of_scope_vapes_and_nicotine_products"),
        ("D17", "out_of_scope_crew"),
        ("D18", "evasion"),
        ("D19", "injection"),
    ],
)
def test_guard_refuses_dev_refusals(item_id, reason) -> None:
    g = check_question(DEV[item_id]["question"])
    assert (g.action, g.reason) == ("refuse", reason)


@pytest.mark.parametrize(
    "item_id", [i for i, d in DEV.items() if d["gold"]["outcome"] != "refused"]
)
def test_guard_passes_normal_dev_questions(item_id) -> None:
    assert check_question(DEV[item_id]["question"]).action == "pass"


@pytest.mark.parametrize(
    "q",
    [
        "Do I have to declare 2 bottles of port from Porto?",
        "Direct flight from Tortola, British Virgin Islands, with 2 bottles of rum",
        "What happens at customs with 3 bottles of wine?",
    ],
)
def test_guard_is_not_trigger_happy(q) -> None:
    assert check_question(q).action == "pass"


def test_guard_notes_other_goods_without_refusing() -> None:
    g = check_question("2 bottles of gin and some cheese from France")
    assert g.action == "pass" and g.other_goods


def test_sanitiser_drops_planted_text_only() -> None:
    planted = DEV["D20"]["inject_into_retrieval"]["text"]
    assert sanitise_clause(planted)[0] is False
    assert sanitise_clause("(a) Application of exemption. The exemption from duty ...")[
        0
    ]


def test_sanitiser_keeps_every_real_chunk() -> None:
    path = ROOT / "data" / "rag-corpus" / "corpus" / "chunks.jsonl"
    if not path.exists():
        pytest.skip("corpus not built")
    chunks = [json.loads(x) for x in path.read_text().splitlines()]
    assert [c["chunk_id"] for c in chunks if not sanitise_clause(c["text"])[0]] == []


# ------------------------------------------------------------------ intake


def test_intake_whatif_keeps_the_product_with_quantity_one() -> None:
    r = IntakeResult.model_validate(
        {
            "request_kind": "assess",
            "profile": {"age": 35},
            "basket": [
                {
                    "item": "wine",
                    "category": "alcohol",
                    "type": "wine",
                    "quantity": {"value": 0, "unit": "bottle"},
                }
            ],
            "owe_less_than_usd": 5,
        }
    )
    assert r.basket[0].quantity.value == 1 and r.owe_less_than_usd == 5


def test_intake_drops_lines_without_quantity_otherwise() -> None:
    r = IntakeResult.model_validate(
        {
            "request_kind": "assess",
            "profile": {"age": 0},
            "basket": [
                {
                    "item": "wine",
                    "category": "alcohol",
                    "type": "wine",
                    "quantity": None,
                }
            ],
            "owe_less_than_usd": 0,
        }
    )
    assert r.basket == [] and r.profile.age is None and r.owe_less_than_usd is None


# ------------------------------------------------------------------ router


ROUTABLE = [i for i, d in DEV.items() if d["facts"] and d["facts"].get("basket")]


@pytest.mark.parametrize("item_id", ROUTABLE)
def test_router_matches_dev_gold_and_passes_gold_citations(item_id) -> None:
    d = DEV[item_id]
    g = d["gold"]
    r = route(
        profile_from_fact(d["facts"]["profile"]),
        [line_from_fact(f) for f in d["facts"]["basket"]],
    )
    assert r.outcome == g["outcome"]
    if g["outcome"] == "clarify":
        assert r.missing == g["clarify_facts"]
        return
    assert r.line_types == [b["type"] for b in g["bottom_line"]]
    # every gold citation is among the ids handed to search (5-clause budget)
    assert set(g.get("citations") or []) <= set(r.citations[:5])


# ------------------------------------------------------------------ verifier


def _verify(out: WriterOut, total="2.97") -> list[str]:
    tools = '{"duty_usd": "2.40", "excise_usd": "0.57", "total_usd": "2.97", "excess_l": "2.000", "duty_rate": "0.03", "dutiable_value_usd": "80"}'
    return verify(
        out,
        n_clauses=3,
        tool_json=tools,
        facts_text="4 bottle Italian wine, 750 ml each, $30.00 each",
        question="4 bottles of wine after 10 days in Italy",
        clause_texts=["1 liter of alcoholic beverages; $800"],
        total_owed=Decimal(total) if total else None,
    )


def test_numbers_reads_dollars_and_plain_numbers() -> None:
    d, e = numbers("You owe $2.97: 2 L over, 3% duty, $1,000 band.")
    assert d == {Decimal("2.97"), Decimal(1000)}
    assert {Decimal(2), Decimal(3)} <= e


def test_verifier_passes_a_faithful_answer() -> None:
    assert _verify(WriterOut(**GOOD_D01)) == []


def test_verifier_rejects_an_invented_amount() -> None:
    bad = WriterOut(**{**GOOD_D01, "explanation": "You owe about $3.10 in total."})
    assert any("$3.1" in p for p in _verify(bad))


def test_verifier_requires_the_total_in_the_bottom_line() -> None:
    bad = WriterOut(**{**GOOD_D01, "bottom_line": "You owe a little duty on the wine."})
    assert any("total owed" in p for p in _verify(bad))


def test_verifier_rejects_unknown_sources_and_evasion() -> None:
    bad = WriterOut(
        **{**GOOD_D01, "sources": [7], "explanation": "Just hide one bottle."}
    )
    problems = _verify(bad)
    assert any("sources" in p for p in problems)
    assert any("declare" in p for p in problems)


# ------------------------------------------------------------------ pipeline


def test_d01_end_to_end() -> None:
    llm = ScriptedLLM(
        intake=[intake_for("D01")],
        writer=[GOOD_D01],
        verifier=[{"advises_evasion": False}],
    )
    run = answer_question(DEV["D01"]["question"], llm=llm, search=fake_search)
    a = run.answer
    assert run.error is None, run.error
    assert a.outcome == "answered"
    assert (a.duty_usd, a.excise_usd, a.total_usd) == (2.4, 0.57, 2.97)
    assert [b.type for b in a.bottom_line] == ["owe"]
    assert set(DEV["D01"]["gold"]["citations"]) <= set(a.citations)
    assert set(a.citations) <= set(run.retrieved_ids)
    assert llm.calls == ["intake", "writer", "verifier"]
    assert "Estimate only" in a.message and run.card["facts_relied_on"]


def test_writer_gets_one_retry_then_escalates() -> None:
    bad = {**GOOD_D01, "bottom_line": "You owe $5.00."}
    llm = ScriptedLLM(
        intake=[intake_for("D01")],
        writer=[bad, bad],
        verifier=[{"advises_evasion": False}],
    )
    run = answer_question(DEV["D01"]["question"], llm=llm, search=fake_search)
    assert run.answer.outcome == "escalated" and run.reason == "verifier_failed"
    assert llm.calls == ["intake", "writer", "writer"]


def test_writer_retry_can_recover() -> None:
    bad = {**GOOD_D01, "bottom_line": "You owe $5.00."}
    llm = ScriptedLLM(
        intake=[intake_for("D01")],
        writer=[bad, GOOD_D01],
        verifier=[{"advises_evasion": False}],
    )
    run = answer_question(DEV["D01"]["question"], llm=llm, search=fake_search)
    assert run.answer.outcome == "answered"


def test_refusal_never_calls_the_model() -> None:
    llm = ScriptedLLM()
    run = answer_question(DEV["D19"]["question"], llm=llm, search=fake_search)
    assert run.answer.outcome == "refused" and llm.calls == []


def test_clarify_asks_the_tools_missing_facts() -> None:
    llm = ScriptedLLM(intake=[intake_for("D14")])
    q = DEV["D14"]["question"]
    llm.by_stage["intake"] = [
        {
            "request_kind": "assess",
            "profile": {"age": 41, "trip": {"value": 4, "unit": "days"}},
            "basket": [
                {
                    "item": "gin",
                    "category": "alcohol",
                    "type": "spirits",
                    "quantity": {"value": 2, "unit": "bottle"},
                    "size": {"value": 70, "unit": "cl"},
                    "abv": 40,
                    "unit_price_usd": 30,
                }
            ],
        }
    ]
    run = answer_question(q, llm=llm, search=fake_search)
    assert run.answer.outcome == "clarify"
    assert run.answer.clarify_facts == DEV["D14"]["gold"]["clarify_facts"]
    assert llm.calls == ["intake"]


def test_planted_document_is_dropped_before_the_writer() -> None:
    seen = {}

    class Spy(ScriptedLLM):
        def chat(self, messages, *, stage, **kw):
            if stage == "writer":
                seen["text"] = messages[-1]["content"]
            return super().chat(messages, stage=stage, **kw)

    good = {
        "bottom_line": "You owe $0.35 on the wine.",
        "explanation": "Declare it.",
        "sources": [1],
    }
    llm = Spy(
        intake=[intake_for("D20")], writer=[good], verifier=[{"advises_evasion": False}]
    )
    run = answer_question(
        DEV["D20"]["question"],
        llm=llm,
        search=fake_search,
        inject=DEV["D20"]["inject_into_retrieval"],
    )
    assert run.answer.outcome == "answered"
    assert (
        "planted-limit-note" not in seen["text"]
        and "planted-limit-note" not in run.retrieved_ids
    )
    for s in DEV["D20"]["gold"]["must_not_contain"]:
        assert s not in json.dumps(run.answer.model_dump())


def test_whatif_end_to_end() -> None:
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
        writer=[
            {
                "bottom_line": "Up to 7 bottles owe $4.59.",
                "explanation": "Declare them.",
                "sources": [1],
            }
        ],
        verifier=[{"advises_evasion": False}],
    )
    run = answer_question(DEV["D12"]["question"], llm=llm, search=fake_search)
    g = DEV["D12"]["gold"]["whatif"]
    assert run.error is None, run.error
    assert run.answer.whatif.max_units == g["max_units"]
    assert run.answer.whatif.owed_usd == g["owed_usd"]


def test_run_agent_writes_and_scores(tmp_path) -> None:
    from eval.run_agent import run

    s = run(
        ScriptedLLM(),
        fake_search,
        "dev",
        "router",
        "t",
        only=["D16", "D18", "D19"],
        results=tmp_path,
    )
    assert s["n"] == 3 and s["accuracy"] == 1.0
    recs = [
        json.loads(x)
        for x in (tmp_path / "runs" / "t" / "router.jsonl").read_text().splitlines()
    ]
    assert [r["reason"] for r in recs] == [
        "out_of_scope_vapes_and_nicotine_products",
        "evasion",
        "injection",
    ]


# ------------------------------------------------------------------ countries (intake output -> ISO codes)


@pytest.mark.parametrize(
    "name,code",
    [
        ("Italy", "IT"),
        ("IT", "IT"),
        ("Cuba", "CU"),
        ("Cuban", "CU"),
        ("Russia", "RU"),
        ("Scotland", "GB"),
        ("UK", "GB"),
        ("Mexico", "MX"),
        ("Trinidad", "TT"),
        ("Republic of Korea", "KR"),  # fuzzy matching would say North Korea
        ("Kraków", None),
        ("duty-free", None),
        ("XX", None),
    ],
)
def test_country_names_to_iso(name, code) -> None:
    from src.agent.countries import to_iso2

    assert to_iso2(name) == code


def test_intake_countries_are_normalised_before_the_tools() -> None:
    from src.agent.intake import normalise_countries

    r = IntakeResult.model_validate(
        {
            "request_kind": "assess",
            "profile": {"age": 45, "direct_arrival_from": "Mexico"},
            "basket": [
                {
                    "item": "cigars",
                    "category": "tobacco",
                    "type": "cigars",
                    "quantity": {"value": 1, "unit": "box of 10"},
                    "origin": "Cuba",
                    "bought_where": "Cancún",
                },
                {
                    "item": "wine",
                    "category": "alcohol",
                    "type": "wine",
                    "quantity": {"value": 1, "unit": "bottle"},
                    "origin": "Atlantis",
                    "bought_where": "duty-free",
                },
            ],
        }
    )
    out, changes = normalise_countries(r)
    assert out.profile.direct_arrival_from == "MX"
    assert out.basket[0].origin == "CU" and out.basket[0].bought_where == "Cancún"
    assert out.basket[1].origin is None  # unrecognised: clarify asks if it matters
    assert out.basket[1].bought_where == "duty-free"
    assert any("Cuba" in c for c in changes)


# ------------------------------------------------------------------ grounding (no guessed facts)


@pytest.mark.parametrize("item_id", [i for i, d in DEV.items() if d["facts"]])
def test_grounding_never_drops_a_stated_fact(item_id) -> None:
    from src.agent.intake import ground_in_question

    f = DEV[item_id]["facts"]["profile"]
    prof = {k: v for k, v in f.items() if v is not None}
    prof.setdefault("age", 33)
    prof.setdefault("trip", {"value": 1, "unit": "days"})
    r = IntakeResult.model_validate({"request_kind": "assess", "profile": prof})
    out, _ = ground_in_question(r, DEV[item_id]["question"])
    if f.get("age") is not None:
        assert out.profile.age == f["age"]
    if f.get("trip") is not None:
        assert out.profile.trip is not None


def test_grounding_drops_guessed_age_and_trip() -> None:
    from src.agent.intake import ground_in_question

    r = IntakeResult.model_validate(
        {
            "request_kind": "assess",
            "profile": {"age": 30, "trip": {"value": 1, "unit": "days"}},
        }
    )
    out, dropped = ground_in_question(r, DEV["D13"]["question"])
    assert out.profile.age is None and out.profile.trip is None and len(dropped) == 2


@pytest.mark.parametrize(
    "q",
    [
        "Day trip to Tijuana",
        "back after a week in Rome",
        "overnight in Montreal",
        "3 nights in Paris",
        "a fortnight in Spain",
    ],
)
def test_grounding_keeps_trip_phrasings(q) -> None:
    from src.agent.intake import ground_in_question

    r = IntakeResult.model_validate(
        {"request_kind": "assess", "profile": {"trip": {"value": 1, "unit": "days"}}}
    )
    assert ground_in_question(r, q)[0].profile.trip is not None


# ------------------------------------------------------------------ origin stated in the question


@pytest.mark.parametrize(
    "item_id", [i for i, d in DEV.items() if d["facts"] and d["facts"].get("basket")]
)
def test_origin_from_question_never_contradicts_gold(item_id) -> None:
    from src.agent.intake import origin_from_question

    d = DEV[item_id]
    basket = [
        line_from_fact(f).model_dump(mode="json", exclude_none=True)
        for f in d["facts"]["basket"]
    ]
    gold = [b.get("origin") for b in basket]
    for b in basket:
        b["origin"] = "MX"  # a wrong model origin on every line
    r = IntakeResult.model_validate(
        {"request_kind": "assess", "profile": {}, "basket": basket}
    )
    out, changes = origin_from_question(r, d["question"])
    for g, b in zip(gold, out.basket, strict=True):
        assert b.origin in (g, "MX")  # either fixed to the stated origin or left alone
    if item_id == "D08":
        assert out.basket[0].origin == "CU" and changes


def test_cuban_cigars_bought_in_cancun_end_to_end() -> None:
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {
                    "age": 45,
                    "trip": {"value": 5, "unit": "days"},
                    "direct_arrival_from": "MX",
                },
                "basket": [
                    {
                        "item": "tobacco",
                        "category": "tobacco",
                        "type": "cigars",
                        "quantity": {"value": 1, "unit": "box of 10"},
                        "origin": "MX",
                        "bought_where": "MX",
                    }
                ],
            }
        ],
        writer=[
            {
                "bottom_line": "The cigars are prohibited.",
                "explanation": "Cuban-origin tobacco cannot be brought in. Declare it.",
                "sources": [1],
            }
        ],
        verifier=[{"advises_evasion": False}],
    )
    run = answer_question(DEV["D08"]["question"], llm=llm, search=fake_search)
    assert run.answer.outcome == "answered"
    assert [b.type for b in run.answer.bottom_line] == ["prohibited"]
    assert set(DEV["D08"]["gold"]["citations"]) <= set(run.answer.citations)
