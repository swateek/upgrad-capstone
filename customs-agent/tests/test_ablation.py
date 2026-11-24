"""eval/ablation.py: every arm reads its own run files; the table matches the run summaries."""

from __future__ import annotations

import json

from eval import ablation


def test_every_arm_has_its_runs():
    for _set, _arm, _agent, mode, dirs in ablation.ARMS:
        for d in dirs:
            assert (ablation.RUNS / d / f"summary_{mode}.json").exists(), d


def test_rows_copy_the_summaries():
    rows = {
        (r["set"], r["arm"]): r for r in [ablation.arm_row(*a) for a in ablation.ARMS]
    }
    s = json.loads(
        (ablation.RUNS / "official-v2-eval3-router" / "summary_router.json").read_text()
    )
    r = rows[("eval-v3", "agent v2, code router")]
    assert r["accuracy"] == s["accuracy"] and r["tokens_per_q"] == round(
        s["tokens_per_q"]
    )
    assert rows[("eval-v3", "agent v2, LLM planner")]["runs"] == 3


def test_metrics_clarify_precision_and_recall():
    """eval-v3, agent v2 router: 23 asks, 10 of them where gold asks, all 10 gold asks asked."""
    from eval.metrics import run_metrics

    m = run_metrics("official-v2-eval3-router", "router")
    assert (m["clarify_asked"], m["clarify_gold"]) == (23, 10)
    assert m["clarify_precision"] == round(10 / 23, 3) and m["clarify_recall"] == 1.0
    assert m["completion"] == 1.0


def test_recall_vs_accuracy_v2_eval3():
    from eval.recall_vs_accuracy import run_rows

    s, items = run_rows(
        "eval-v3",
        "agent v2, code router",
        "official-v2-eval3-router",
        "router",
        "eval_set_v3.jsonl",
    )
    assert s["questions_searched"] == len(items) == 61
    assert {x["id"] for x in items if not x["full_recall"]} == {
        "E3-022",
        "E3-034",
        "E3-043",
        "E3-044",
    }
