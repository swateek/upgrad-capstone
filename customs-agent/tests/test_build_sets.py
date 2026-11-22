"""The multi-turn conversations and the red-team list: well-formed, gold from the right place."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.build_conversations import load, scenarios
from eval.build_redteam import build

EVAL = Path(__file__).parents[1] / "eval"
DEV = {
    json.loads(x)["id"]: json.loads(x)
    for x in (EVAL / "dev_set.jsonl").read_text().splitlines()
}
CONVS = [json.loads(x) for x in (EVAL / "conversations.jsonl").read_text().splitlines()]


def test_conversation_source_is_valid_and_matches_the_built_file() -> None:
    convs = load()
    assert [c["id"] for c in convs] == [c["id"] for c in CONVS]
    assert sum(len(c["turns"]) for c in convs) == sum(len(c["turns"]) for c in CONVS)
    answered = scenarios(convs)
    built = [t for c in CONVS for t in c["turns"] if "facts" in t]
    assert len(answered) == len(built)


@pytest.mark.parametrize("conv", CONVS, ids=[c["id"] for c in CONVS])
def test_each_turn_has_gold_of_its_kind(conv) -> None:
    for t in conv["turns"]:
        g = t["gold"]
        assert ("user" in t) != ("edit" in t)
        if g["outcome"] == "clarify":
            assert g["clarify_facts"]
        if g["outcome"] == "answered":
            assert "facts" in t and g["bottom_line"]


def test_dollar_gold_comes_from_the_workbook() -> None:
    totals = {
        (c["id"], t["turn"]): t["gold"].get("total_usd")
        for c in CONVS
        for t in c["turns"]
    }
    assert (
        totals[("C01", 2)] == 1.46
        and totals[("C03", 2)] == 3.12
        and totals[("C13", 2)] == 0
    )


def test_redteam_copies_gold_from_its_source() -> None:
    items = {i["id"]: i for i in build()}
    assert len(items) >= 15
    t17 = items["T17"]
    assert (
        t17["gold"]["total_usd"] == DEV["D11"]["gold"]["total_usd"]
        and t17["facts"] == DEV["D11"]["facts"]
    )
    assert "X1234567" in items["T20"]["gold"]["must_not_contain"]
    assert items["T06"]["inject_into_retrieval"]["doc_id"] == "planted-italy-note"
    assert (
        items["T01"]["gold"]["outcome"] == "refused" and items["T01"]["facts"] is None
    )


def test_redteam_file_is_current() -> None:
    built = [json.loads(x) for x in (EVAL / "redteam.jsonl").read_text().splitlines()]
    assert built == build()
