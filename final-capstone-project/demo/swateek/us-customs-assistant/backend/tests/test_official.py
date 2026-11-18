"""Official-run tooling, offline: pre-flight pins both freezes; the failure classifier and the
report work on run records."""

from eval import eval_report as er
from eval import official


def test_preflight_pins_the_freezes():
    pins = official.preflight()
    assert pins["agent_freeze"] >= 4 and pins["eval_version"] == 1
    assert pins["caps"] == {"tokens": 12000, "model_calls": 10, "tool_calls": 10}


def test_plan_covers_the_runs_in_the_plan():
    names = [r for r, _, _ in official.RUNS]
    assert names.count("planner-1") == 1 and sum(n.endswith("-corr") for n in names) == 3
    assert {m for _, _, m in official.RUNS} == {"planner", "router", "tool_calling", "single_rag"}


def turn(correct, labels, outcome="answered", kind="owe", gold="answered", events=(), esc=None):
    meta = {"events": list(events), "model_calls": 4, "tool_calls": 3, "tokens": 3000,
            "seconds": 12.0, **({"escalation": esc} if esc else {})}  # fmt: skip
    return {"turn": 1, "gold_outcome": gold, "gold_kind": "owe", "gold_owe": "1.00",
            "gold_clarify_fields": [], "correct": correct, "labels": labels,
            "score": {"owe_ok": correct, "cite_ok": True, "claims": 2, "claims_met": 2},
            "card": {"outcome": outcome, "kind": kind, "owe_usd": "1.00", "sources": [],
                     "meta": meta}}  # fmt: skip


def rec(t, mode="planner", category="alcohol_excess_800", ext=(10, 10, 0)):
    return {
        "id": "X",
        "category": category,
        "mode": mode,
        "turns": [t],
        "extraction": {"fields": ext[0], "correct": ext[1], "invented": ext[2]},
    }


def test_classifier_rules():
    c = er.classify
    assert c(rec(t := turn(False, ["wrong_amount"]), ext=(10, 9, 0)), t) == "extraction_error"
    assert c(rec(t := turn(False, ["wrong_amount"])), t) == "rule_selection_error"
    assert c(rec(t := turn(False, ["wrong_amount"]), mode="single_rag"), t) == "invented_figure"
    tc = [{"event": "tool_calling", "transcription_diffs": 1}]
    assert (
        c(rec(t := turn(False, ["wrong_amount"], events=tc), mode="tool_calling"), t)
        == "tool_arg_error"
    )
    assert c(rec(t := turn(False, ["no_clarify"], gold="clarify")), t) == "clarify_miss"
    esc = turn(
        False,
        ["wrong_outcome:answered->escalated"],
        "escalated",
        "escalated",
        esc="verifier_failed",
    )
    assert c(rec(esc), esc) == "unsupported_claim"
    assert c(rec(t := turn(False, ["wrong_amount"]), category="whatif"), t) == "feature_not_built"
    assert c(rec(t := turn(False, ["missing_citation"])), t) == "citation_mapping"


def test_metrics_and_buckets():
    recs = [rec(turn(True, [])), rec(turn(False, ["wrong_amount"]), ext=(10, 9, 0))]
    m = er.run_metrics(recs, usd_per_m=0.10)
    assert m["turn_accuracy"] == 0.5 and m["failures"] == {"extraction_error": 1}
    assert m["cost_per_1k_turns_usd"] == 3000 * 0.10 / 1e3
    assert {r["bucket"] for r in m["failure_rows"]} == {"Reasoning error"}


def test_classifier_fixes_from_the_hand_check():
    c = er.classify
    miss = turn(False, ["wrong_outcome:refused->clarify"], "clarify", "clarify", gold="refused")
    assert c(rec(miss), miss) == "refusal_miss"
    t = turn(False, ["missing_citation"])
    assert c(rec(t, ext=(12, 11, 0)), t) == "extraction_error"


def test_hand_label_replaces_the_automatic_one_for_its_runs():
    recs = [rec(turn(False, ["wrong_amount"]))]
    hand = [{"id": "X", "turn": 1, "runs": ["planner-1"], "auto": "rule_selection_error",
             "hand": "unit_error"}]  # fmt: skip
    m = er.run_metrics(recs, None, "planner-1", hand)
    assert m["failures"] == {"unit_error": 1}
    assert m["failure_rows"][0]["auto"] == "rule_selection_error"
    assert m["failure_rows"][0]["hand_checked"]
    assert er.run_metrics(recs, None, "router", hand)["failures"] == {"rule_selection_error": 1}
    assert {h["hand"] for h in er.hand_labels()} <= set(er.BUCKETS)
