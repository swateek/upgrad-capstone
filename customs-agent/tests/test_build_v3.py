"""eval-v3 / dev-v2 pipeline: the independent rule check, corrections, split, allocation, citations."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))

import build_v3
import check_v3

WINE = {
    "item": "Rioja",
    "category": "alcohol",
    "type": "wine",
    "quantity": {"value": 3, "unit": "bottle"},
    "unit_ml": 750,
    "abv": 13,
    "unit_price_usd": 20,
    "origin": "ES",
    "bought_where": "ES",
    "excise_class": "wine_still_le16",
}
GIN = {
    "item": "gin",
    "category": "alcohol",
    "type": "spirits",
    "quantity": {"value": 1, "unit": "bottle"},
    "unit_ml": 700,
    "abv": 43,
    "unit_price_usd": 35,
    "origin": "GB",
    "bought_where": "GB",
    "excise_class": "spirits",
}
PROFILE = {
    "age": 40,
    "trip": {"value": 8, "unit": "days"},
    "exemption_used_last_30_days": False,
}


def scen(**kw) -> dict:
    s = {
        "id": "T1",
        "type": "mixed_basket",
        "question": "I'm 40, 8 days in Spain, 13%, $20, 43%, $35",
        "profile": dict(PROFILE),
        "basket": [dict(WINE), dict(GIN)],
        "gold": {
            "outcome": "answered",
            "exemption": "standard_800",
            "bottom_line": ["owe", "owe"],
        },
    }
    s.update(kw)
    return s


def test_rules_rank_the_allowance_by_charge_per_litre():
    e = check_v3.expected(scen())
    # the 0.7 L gin (higher charge per litre) goes in first, then 0.3 L of the 2.25 L wine
    assert e["bottom_line"] == ["owe", "nothing_to_pay"]
    s = scen()
    build_v3.allocate(s)
    assert [b["gold_exempt_l"] for b in s["basket"]] == [0.3, 0.7]


def test_check_flags_the_known_generator_slips():
    s = scen(
        profile={**PROFILE, "trip": {"value": 4, "unit": "days"}},
        basket=[{**GIN, "quantity": {"value": 1, "unit": "bottle"}}],
        gold={
            "outcome": "answered",
            "exemption": "none_200_failed",
            "bottom_line": ["owe"],
        },
    )
    issues = check_v3.check(s, "t").issues
    assert any(
        "exemption none_200_failed / rules say standard_800" in i for i in issues
    )
    s = scen(
        gold={
            "outcome": "answered",
            "exemption": "standard_800",
            "bottom_line": ["owe", "owe", "owe"],
        }
    )
    assert any(i.startswith("bottom line") for i in check_v3.check(s, "t").issues)


def test_clarify_rules_follow_spec_v2():
    rum = {
        **GIN,
        "item": "rum",
        "origin": None,
        "abv": None,
        "unit_ml": 1000,
        "quantity": {"value": 2, "unit": "bottle"},
    }
    s = scen(
        type="clarify",
        profile={
            "trip": {"value": 9, "unit": "days"},
            "exemption_used_last_30_days": False,
        },
        basket=[rum],
        gold={"outcome": "clarify", "clarify_facts": ["age", "origin", "abv"]},
    )
    assert sorted(check_v3.expected_clarify(s)) == [
        "abv",
        "age",
        "origin",
    ]  # 2 L > 1 L: ABV in stage 1
    cab = {**WINE, "origin": None, "bought_where": "CL"}
    s = scen(
        type="clarify",
        basket=[cab],
        gold={"outcome": "clarify", "clarify_facts": ["origin"]},
    )
    assert check_v3.expected_clarify(s) == [
        "origin"
    ]  # bought in a 0%-duty country (SPEC v2 11)


def test_citations_follow_the_eval_v2_conventions():
    assert build_v3.citations(scen()) == [
        "19cfr148.33",
        "htsus9816.00.20",
        "ttb-tax-rates",
    ]
    cuban = scen(
        basket=[
            {
                **GIN,
                "category": "tobacco",
                "type": "cigars",
                "origin": "CU",
                "count": 25,
            }
        ],
        gold={"outcome": "answered", "bottom_line": ["prohibited"]},
    )
    assert build_v3.citations(cuban) == ["31cfr515.204", "31cfr515.585"]
    mx = scen(
        profile={
            **PROFILE,
            "trip": {"value": 6, "unit": "hours"},
            "direct_arrival_from": "MX",
        },
        gold={
            "outcome": "answered",
            "exemption": "standard_800",
            "bottom_line": ["nothing_to_pay", "owe"],
        },
    )
    assert "19cfr148.35" in build_v3.citations(mx)
    assert (
        build_v3.citations(
            scen(gold={"outcome": "escalated", "reason": "commercial_quantity"})
        )
        == []
    )


def test_built_sets_are_complete_and_clean():
    sc = yaml.safe_load((ROOT / "eval" / "scenarios_v3.yaml").read_text())["scenarios"]
    sets = Counter(s["set"] for s in sc)
    assert sets["eval3"] == 100 and sets["dev2"] >= 50
    # E3-019: the one known gold error, found on Day 11 (eval-v3 is tagged; logged as an erratum)
    flagged = {s["id"] for s in sc if check_v3.check(s, s["generator"]).issues}
    assert flagged == {"E3-019"}
    ev = [json.loads(line) for line in (ROOT / "eval" / "eval_set_v3.jsonl").open()]
    dv = [json.loads(line) for line in (ROOT / "eval" / "dev_set_v2.jsonl").open()]
    assert len(ev) == 100 and len(dv) == sets["dev2"]
    assert not {r["question"] for r in ev} & {r["question"] for r in dv}
    for r in ev + dv:  # every answered alcohol answer has dollar gold or none is owed
        if (
            r["gold"]["outcome"] == "answered"
            and r["type"] not in ("whatif",)
            and r["gold"].get("lines")
        ):
            assert r["gold"]["total_usd"] >= 0
    assert {t for t in Counter(r["type"] for r in ev)} == {
        t for t in Counter(r["type"] for r in dv)
    }


def test_checker_catches_a_wine_band_that_disagrees_with_the_abv():
    """Day 11: E3-019's 15.5% wine was labelled over 16% by its generator."""
    items = yaml.safe_load((ROOT / "eval" / "scenarios_v3.yaml").read_text())[
        "scenarios"
    ]
    s = next(x for x in items if x["id"] == "E3-019")
    assert any("not wine_still_16_21" in i for i in check_v3.check(s, "v3").issues)
