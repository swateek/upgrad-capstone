"""The calculators against the dev-set gold (eval/dev_set.jsonl).

Only the dev set: nothing is tuned against eval-v1 (CLAUDE.md rule 6). Gold comes from
eval/gold.xlsx, independent of this code (rule 5).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.tools.common import dec
from src.tools.whatif_optimise import Args as WArgs
from src.tools.whatif_optimise import whatif_optimise
from tests._chain import line_from_fact, profile_from_fact, run

DEV = [
    json.loads(x)
    for x in (Path(__file__).parents[1] / "eval" / "dev_set.jsonl")
    .read_text()
    .splitlines()
]
CALC = [
    s
    for s in DEV
    if s["facts"]
    and s["gold"]["outcome"] in ("answered", "clarify", "escalated")
    and "whatif" not in s["gold"]
]
WHATIF = [s for s in DEV if "whatif" in s["gold"]]


def _inputs(s: dict):
    return profile_from_fact(s["facts"]["profile"]), [
        line_from_fact(f) for f in s["facts"]["basket"]
    ]


@pytest.mark.parametrize("s", CALC, ids=[s["id"] for s in CALC])
def test_dev_scenario(s: dict) -> None:
    gold = s["gold"]
    result = run(*_inputs(s))
    assert result["outcome"] == gold["outcome"], result
    if gold["outcome"] == "clarify":
        assert result["missing"] == gold["clarify_facts"]
        return
    if gold["outcome"] != "answered":
        return
    assert result["bottom_line"] == [b["type"] for b in gold["bottom_line"]]
    if "total_usd" in gold:
        de = result["duty"]
        assert de.total_usd == dec(gold["total_usd"])
        assert de.duty_usd == dec(gold["duty_usd"])
        assert de.excise_usd == dec(gold["excise_usd"])
        by_line = {d.line: d for d in de.lines}
        for g in gold["lines"]:
            if Decimal(str(g["excess_l"])) == 0:
                assert g["line"] not in by_line
                continue
            d = by_line[g["line"]]
            assert d.excess_l == dec(g["excess_l"])
            assert d.dutiable_value_usd == dec(g["dutiable_value_usd"])
            assert d.duty_usd == dec(g["duty_usd"])
            assert d.excise_usd == dec(g["excise_usd"])


@pytest.mark.parametrize("s", WHATIF, ids=[s["id"] for s in WHATIF])
def test_dev_whatif(s: dict) -> None:
    w = s["facts"]["whatif"]
    profile = profile_from_fact(s["facts"]["profile"])
    product = line_from_fact(
        {
            "item": w["item"],
            "category": "alcohol",
            "type": "wine",  # D12 is still wine; what-if facts name the product only
            "quantity": {"value": 1, "unit": "bottle"},
            "unit_ml": w["unit_ml"],
            "abv": w["abv"],
            "unit_price_usd": w["unit_price_usd"],
            "origin": w["origin"],
        }
    )
    got = whatif_optimise(
        WArgs(
            profile=profile, product=product, owe_less_than_usd=w["owe_less_than_usd"]
        )
    )
    assert got.max_units == s["gold"]["whatif"]["max_units"]
    assert got.owed_usd == dec(s["gold"]["whatif"]["owed_usd"])
