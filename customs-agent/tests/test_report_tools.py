"""Day 12 report helpers: the token-distribution table and the figure label groups."""

import csv

from eval import report_figures, token_calls


def test_quantile_is_a_real_value_nearest_rank():
    v = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert token_calls.quantile(v, 0.5) == 50
    assert token_calls.quantile(v, 0.95) == 100
    assert token_calls.quantile([7], 0.95) == 7
    assert token_calls.quantile([], 0.5) == 0


def test_repair_calls_count_under_their_stage():
    assert token_calls.stage_of("intake_repair") == "intake"
    assert token_calls.stage_of("writer") == "writer"


def test_failure_groups_do_not_overlap():
    seen = set()
    for _, codes in report_figures.STAGES:
        assert not (codes & seen)
        seen |= codes


def test_final_label_uses_agreed_hand_label(tmp_path):
    p = tmp_path / "f.csv"
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["label", "human_label", "human_label_2"])
        w.writeheader()
        w.writerow({"label": "RULES", "human_label": "GOLD_ERROR", "human_label_2": "GOLD_ERROR"})
        w.writerow({"label": "GUARD_MISS", "human_label": "GUARD_MISS", "human_label_2": "OTHER"})
        w.writerow({"label": "EXTRACT_MISSED", "human_label": "", "human_label_2": ""})
    c = report_figures.final_labels(p)
    assert c == {"GOLD_ERROR": 1, "GUARD_MISS": 1, "EXTRACT_MISSED": 1}
