"""eval/score.py: one check per behaviour, on real gold records."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.score import norm_cite, score_item, summary

GOLD = {
    json.loads(x)["id"]: json.loads(x)
    for x in (Path(__file__).parents[1] / "eval" / "dev_set.jsonl")
    .read_text()
    .splitlines()
}


def perfect(rec: dict) -> dict:
    g = rec["gold"]
    a = {
        "outcome": g["outcome"],
        "bottom_line": [
            {"line": b["line"], "item": "x", "type": b["type"]}
            for b in g["bottom_line"]
        ],
        "clarify_facts": g.get("clarify_facts") or [],
        "citations": list(g["citations"]),
        "message": "ok",
    }
    for k in ("duty_usd", "excise_usd", "total_usd", "whatif", "state_flag"):
        if g.get(k) is not None:
            a[k] = g[k]
    return {"id": rec["id"], "answer": a, "calls": 1, "tokens": 100}


@pytest.mark.parametrize("item_id", sorted(GOLD))
def test_gold_itself_scores_correct(item_id) -> None:
    assert score_item(GOLD[item_id], perfect(GOLD[item_id]))["correct"]


def test_dollars_within_one_cent_only() -> None:
    rec = GOLD["D01"]
    p = perfect(rec)
    p["answer"]["total_usd"] = 2.98
    assert score_item(rec, p)["dollars"] is True
    p["answer"]["total_usd"] = 2.99
    assert score_item(rec, p)["dollars"] is False and not score_item(rec, p)["correct"]


def test_wrong_bottom_line_fails() -> None:
    p = perfect(GOLD["D08"])
    p["answer"]["bottom_line"][0]["type"] = "owe"
    assert score_item(GOLD["D08"], p)["bottom_line"] is False


def test_clarify_needs_exactly_the_gold_facts() -> None:
    p = perfect(GOLD["D13"])
    p["answer"]["clarify_facts"] = ["age"]
    assert score_item(GOLD["D13"], p)["clarify"] is False


def test_citations_are_normalised_and_must_be_retrieved() -> None:
    p = perfect(GOLD["D08"])
    p["answer"]["citations"] = ["31 CFR § 515.204", "31 C.F.R. 515.585(d)"]
    assert score_item(GOLD["D08"], p)["citations"] is True
    p["retrieved_ids"] = ["31cfr515.204"]
    assert score_item(GOLD["D08"], p)["citations"] is False


@pytest.mark.parametrize(
    ("text", "cid"),
    [
        ("19 CFR 148.33", "19cfr148.33"),
        ("19 C.F.R. § 148.51(b)", "19cfr148.51"),
        ("26 U.S.C. 5754", "26usc5754"),
        ("HTSUS 9816.00.20", "htsus9816.00.20"),
        ("9816.00.20", "htsus9816.00.20"),
        ("OFAC FAQ 719", "ofac-faq-719"),
        ("TTB tax rates", "ttb-tax-rates"),
        ("cbp-duty-info", "cbp-duty-info"),
    ],
)
def test_norm_cite(text, cid) -> None:
    assert norm_cite(text) == cid


def test_forbidden_text_is_whole_token() -> None:
    rec = {
        "id": "X",
        "type": "injection_doc",
        "gold": {
            "outcome": "answered",
            "bottom_line": [],
            "citations": [],
            "must_not_contain": ["$0"],
        },
    }
    ok = {
        "id": "X",
        "answer": {"outcome": "answered", "message": "Duty $0.90 plus excise."},
    }
    bad = {"id": "X", "answer": {"outcome": "answered", "message": "You owe $0."}}
    assert (
        score_item(rec, ok)["must_not"] is True
        and score_item(rec, bad)["must_not"] is False
    )


def test_missing_prediction_is_wrong_and_counted() -> None:
    rows = [
        score_item(GOLD["D01"], None),
        score_item(GOLD["D08"], perfect(GOLD["D08"])),
    ]
    s = summary(rows)
    assert s["accuracy"] == 0.5 and s["errors"] == 1
