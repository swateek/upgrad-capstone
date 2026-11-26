"""gold-v2: eval-v2's questions re-scored under SPEC v2; gold-v1 stays as it was."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

EVAL = Path(__file__).resolve().parents[1] / "eval"
sys.path.insert(0, str(EVAL))
import build_gold_v2


def read(name: str) -> dict[str, dict]:
    return {r["id"]: r for r in map(json.loads, (EVAL / name).open())}


def test_only_listed_ids_differ_from_gold_v1():
    v1, v2 = read("eval_set.jsonl"), read("eval_set_gold_v2.jsonl")
    assert v1.keys() == v2.keys() and len(v1) == 80
    listed = {c["id"] for c in build_gold_v2.changes()}
    moved = {i for i in v1 if v1[i] != v2[i]}
    assert moved == listed


def test_questions_and_facts_unchanged():
    v1, v2 = read("eval_set.jsonl"), read("eval_set_gold_v2.jsonl")
    for i in v1:
        assert v1[i]["question"] == v2[i]["question"]
        assert v1[i]["facts"] == v2[i]["facts"]


def test_sake_taxed_as_beer():
    sc = {
        s["id"]: s
        for s in yaml.safe_load((EVAL / "scenarios_gold_v2.yaml").read_text())[
            "scenarios"
        ]
    }
    for i, line in (("E07", 0), ("E47", 1)):
        assert sc[i]["basket"][line]["item"] == "sake"
        assert sc[i]["basket"][line]["excise_class"] == "beer"
    v2 = read("eval_set_gold_v2.jsonl")
    assert v2["E07"]["gold"]["total_usd"] == 0.61
    assert v2["E47"]["gold"]["total_usd"] == 1.37


def test_every_change_names_its_rule():
    for c in build_gold_v2.changes():
        assert c["rule"].strip() and c["gold_v1"].strip()


def test_review_sample_is_fixed():
    assert (
        build_gold_v2.draw_sample()
        == build_gold_v2.REVIEW_SAMPLE
        == [
            "E08",
            "E14",
            "E15",
            "E32",
            "E40",
            "E43",
            "E44",
            "E49",
            "E57",
            "E66",
            "E71",
            "E77",
        ]
    )


def test_metadata_changes_move_no_scored_field():
    v1, v2 = read("eval_set.jsonl"), read("eval_set_gold_v2.jsonl")
    for c in build_gold_v2.changes():
        if c.get("scored", True):
            continue
        a, b = v1[c["id"]]["gold"], v2[c["id"]]["gold"]
        assert {k for k in a if a[k] != b[k]} == {"exemption"}
    assert v2["E34"]["gold"]["exemption"] is None
