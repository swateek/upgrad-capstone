"""eval/build_paraphrase.py: gold copied from the source dev item; bad input rejected."""

from __future__ import annotations

import json

import pytest

from eval.build_paraphrase import EVAL, build


def write(tmp_path, rows) -> object:
    p = tmp_path / "raw.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def test_gold_and_planted_doc_come_from_the_source(tmp_path) -> None:
    raw = write(
        tmp_path,
        [
            {
                "id": "P01a",
                "source": "D01",
                "question": "Ten days in Italy, four 75 cl bottles of wine...",
                "changed": "units",
            },
            {
                "id": "P20a",
                "source": "D20",
                "question": "Back from Chile after 10 days...",
                "changed": "order",
            },
        ],
    )
    items = build(raw, EVAL / "dev_set.jsonl")
    dev = {
        json.loads(x)["id"]: json.loads(x)
        for x in (EVAL / "dev_set.jsonl").read_text().splitlines()
    }
    assert (
        items[0]["gold"] == dev["D01"]["gold"]
        and items[0]["type"] == "alcohol_excess_800"
    )
    assert items[1]["inject_into_retrieval"] == dev["D20"]["inject_into_retrieval"]
    assert "inject_into_retrieval" not in items[0]


@pytest.mark.parametrize(
    "row,msg",
    [
        ({"id": "P01a", "source": "D02", "question": "x"}, "does not match"),
        ({"id": "Q01a", "source": "D01", "question": "x"}, "not like"),
        ({"id": "P01a", "source": "D01", "question": ""}, "empty"),
        ({"id": "P99a", "source": "D99", "question": "x"}, "unknown source"),
    ],
)
def test_bad_rows_are_rejected(tmp_path, row, msg) -> None:
    with pytest.raises(ValueError, match=msg):
        build(write(tmp_path, [row]), EVAL / "dev_set.jsonl")


def test_copies_and_duplicates_are_rejected(tmp_path) -> None:
    dev0 = json.loads((EVAL / "dev_set.jsonl").read_text().splitlines()[0])
    with pytest.raises(ValueError, match="copy"):
        build(
            write(
                tmp_path,
                [{"id": "P01a", "source": "D01", "question": dev0["question"]}],
            ),
            EVAL / "dev_set.jsonl",
        )
    row = {"id": "P01a", "source": "D01", "question": "x"}
    with pytest.raises(ValueError, match="duplicate"):
        build(write(tmp_path, [row, row]), EVAL / "dev_set.jsonl")
