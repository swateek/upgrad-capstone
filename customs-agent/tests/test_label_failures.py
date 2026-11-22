"""Failure-taxonomy rules (eval/label_failures.py, docs/TAXONOMY.md)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from eval.label_failures import LABELS, label, label_file, severity

ROOT = Path(__file__).resolve().parents[1]

PROFILE = {
    "age": 34,
    "trip": {"value": 10, "unit": "days"},
    "exemption_used_last_30_days": False,
}
WINE = {
    "item": "wine",
    "category": "alcohol",
    "type": "wine",
    "quantity": {"value": 4, "unit": "bottle"},
    "unit_ml": 750,
    "abv": 13,
    "unit_price_usd": 30,
    "origin": "IT",
}
GOLD_ANSWER = {
    "outcome": "answered",
    "bottom_line": [{"line": 1, "type": "owe"}],
    "citations": ["19cfr148.33"],
    "duty_usd": 2.4,
    "excise_usd": 0.57,
    "total_usd": 2.97,
}


def gold(**over) -> dict:
    g = dict(GOLD_ANSWER, **over)
    return {
        "id": "X1",
        "type": "t",
        "facts": {"profile": PROFILE, "basket": [WINE]},
        "gold": g,
    }


def pred(answer: dict, *, trace: list | None = None, **kw) -> dict:
    line = {k: v for k, v in WINE.items() if k != "unit_ml"} | {
        "size": {"value": 750, "unit": "ml"}
    }
    base = [
        {"step": "guard", "action": "pass", "reason": None},
        {
            "step": "intake",
            "output": {"request_kind": "assess", "profile": PROFILE, "basket": [line]},
        },
    ]
    return {
        "id": "X1",
        "strategy": "router",
        "answer": answer,
        "trace": trace or base,
        **kw,
    }


def row(**checks) -> dict:
    return {"correct": False, **checks}


def test_every_label_has_a_definition():
    assert all(LABELS.values())


def test_no_answer_endpoint_vs_crash():
    assert label(gold(), None, row())["label"] == "CRASH"
    p = {"id": "X1", "answer": None, "error": "ReadTimeout: timed out"}
    assert label(gold(), p, row())["label"] == "INFRA"


def test_guard_miss_and_false_refusal():
    g = gold(outcome="refused", reason="evasion")
    lab = label(g, pred({"outcome": "answered"}), row(outcome=False))
    assert (lab["label"], lab["detail"], lab["severity"]) == (
        "GUARD_MISS",
        "evasion",
        "unsafe",
    )
    refused = pred(
        {"outcome": "refused"},
        trace=[{"step": "guard", "action": "refuse", "reason": "evasion"}],
    )
    lab = label(gold(), refused, row(outcome=False))
    assert (lab["label"], lab["severity"]) == ("GUARD_FALSE_REFUSAL", "safe_fail")


def test_intent_when_intake_scopes_out():
    p = pred({"outcome": "refused"})
    p["trace"][1]["output"]["request_kind"] = "evasion"
    assert label(gold(), p, row(outcome=False))["label"] == "INTENT"


def test_invented_fact_beats_later_stages():
    g = gold(outcome="clarify", clarify_facts=["abv"])
    g["facts"]["basket"] = [dict(WINE, abv=None)]
    p = pred({"outcome": "answered", "total_usd": 2.97})
    lab = label(g, p, row(outcome=False, clarify=False))
    assert (lab["label"], lab["detail"], lab["severity"]) == (
        "EXTRACT_INVENTED",
        "item1.abv",
        "unsafe",
    )


def test_missed_size_when_it_asks():
    p = pred({"outcome": "clarify", "clarify_facts": ["size"]})
    p["trace"][1]["output"]["basket"][0].pop("size")
    lab = label(gold(), p, row(outcome=False, bottom_line=False, dollars=False))
    assert (lab["label"], lab["detail"]) == ("EXTRACT_MISSED", "item1.size")
    assert lab["severity"] == "safe_fail"


def test_origin_only_counts_when_it_changes_the_rate():
    p = pred(dict(GOLD_ANSWER, total_usd=3.5))
    p["trace"][1]["output"]["basket"][0]["origin"] = "Italy"  # no programme for IT
    lab = label(gold(), p, row(dollars=False))
    assert lab["label"] == "RULES"  # the origin name is not the cause
    g = gold()
    g["facts"]["basket"] = [dict(WINE, origin="CL")]  # US-Chile FTA: no duty
    p["trace"][1]["output"]["basket"][0]["origin"] = "Chile"
    lab = label(g, p, row(dollars=False))
    assert (lab["label"], lab["detail"]) == ("EXTRACT_WRONG", "item1.origin")


def test_budget_plan_verifier_citations():
    p = pred({"outcome": "escalated"})
    p["trace"].append({"step": "budget", "exceeded": "10 tool steps"})
    assert label(gold(), p, row(outcome=False))["label"] == "BUDGET"

    p = pred({"outcome": "escalated"}, reason="verifier_failed")
    p["trace"].append(
        {"step": "verifier", "attempt": 1, "problems": ["number 1.25 not in tools"]}
    )
    lab = label(gold(), p, row(outcome=False))
    assert (lab["label"], lab["detail"], lab["needs_check"]) == (
        "WRITER",
        "number_not_in_tools",
        True,
    )

    p = pred({"outcome": "escalated"}, error="ToolError: rule_not_found")
    p["trace"].append({"step": "tool_error_router", "error": "rule_not_found"})
    assert label(gold(), p, row(outcome=False))["label"] == "PLAN"

    p = pred(
        dict(GOLD_ANSWER, citations=["19cfr148.35"]), retrieved_ids=["19cfr148.35"]
    )
    assert label(gold(), p, row(citations=False))["label"] == "RETRIEVAL_MISS"
    p["retrieved_ids"].append("19cfr148.33")
    lab = label(gold(), p, row(citations=False))
    assert (lab["label"], lab["severity"]) == ("CITATION_SELECTION", "minor")


@pytest.mark.parametrize(
    ("answer", "want"),
    [
        (
            {
                "outcome": "answered",
                "bottom_line": [{"line": 1, "type": "nothing_to_pay"}],
            },
            "unsafe",
        ),
        (
            {"outcome": "answered", "bottom_line": [{"line": 1, "type": "prohibited"}]},
            "over",
        ),
        (dict(GOLD_ANSWER, total_usd=1.00), "unsafe"),
        (dict(GOLD_ANSWER, total_usd=5.00), "over"),
        ({"outcome": "escalated"}, "safe_fail"),
        (GOLD_ANSWER, "minor"),
    ],
)
def test_severity(answer, want):
    assert severity(GOLD_ANSWER, answer, {}) == want


def test_baseline_arms_get_one_label():
    p = {
        "id": "X1",
        "strategy": "single_rag",
        "answer": {"outcome": "answered"},
        "trace": [],
    }
    assert label(gold(), p, row(dollars=False))["label"] == "END_TO_END_MODEL"


def test_rules_recover_the_documented_causes():
    """The 29 failures fixed on Days 5-7 (docs/COMPENSATIONS.md rows 5-17): the rules must
    give the cause we found by hand. C04-t2 is the known exception: the rules say WRITER and
    flag it for checking; by hand it is a verifier false alarm (the writer was right)."""
    want = list(csv.DictReader((ROOT / "eval" / "taxonomy_check.csv").open()))
    sets = {
        "para-router": "paraphrase",
        "redteam-day7": "redteam",
        "day7-conv": "conversations",
    }
    got: dict[tuple[str, str], dict] = {}
    for run in {w["run"] for w in want}:
        d = ROOT / "results" / "runs" / run
        f = next(d.glob("*.jsonl"))
        for r in label_file(f, sets.get(run, "dev")):
            got[(run, r["id"])] = r
    agree = [
        w for w in want if got[(w["run"], w["id"])]["label"] == w["expected_label"]
    ]
    differ = [w["id"] for w in want if w not in agree]
    assert differ == ["C04-t2"]
    assert got[("day7-conv", "C04-t2")]["needs_check"]
    assert len(agree) == len(want) - 1


def test_agreement_and_kappa():
    from eval.label_failures import agreement

    rows = [
        {"id": "a", "label": "GUARD_MISS", "human_label": "GUARD_MISS"},
        {"id": "b", "label": "WRITER", "human_label": "VERIFIER_FALSE_ALARM"},
        {"id": "c", "label": "EXTRACT_MISSED", "human_label": "EXTRACT_MISSED"},
        {"id": "d", "label": "EXTRACT_MISSED", "human_label": ""},  # not checked yet
    ]
    a = agreement(rows)
    assert (a["n"], a["agreement"]) == (3, 0.667)
    assert a["disagree"] == [("b", "WRITER", "VERIFIER_FALSE_ALARM")]
    assert 0 < a["kappa"] < a["agreement"]
