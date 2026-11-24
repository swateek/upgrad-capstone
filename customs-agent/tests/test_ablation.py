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
