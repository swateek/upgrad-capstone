"""The calculators against the DEV gold (pack/eval/dev.jsonl, built independently, plan D18).

Only the dev set is used here (AGENTS.md: tune on dev only); the frozen eval-v1 gold is for the
official runs. For each dev scenario whose last turn the calculators decide (refusals and
injections are the guard's job), compare outcome, kind, owe, every figure, every note and the
cited rules with the gold of that last turn.
"""

import json
from decimal import Decimal

import pytest

from customs.config import PROJECT_ROOT
from customs.tools.calc import assess
from customs.tools.models import Line, Profile

DEV = PROJECT_ROOT / "pack" / "eval" / "dev.jsonl"
GUARD_CATEGORIES = {"refuse_evasion", "injection_user", "injection_doc"}


def dev_rows():
    rows = [json.loads(line) for line in DEV.read_text(encoding="utf-8").splitlines() if line]
    return [r for r in rows if r["category"] not in GUARD_CATEGORIES]


def refs_as_claims(refs: list[str]) -> set[str]:
    """Our rule refs in the gold's claim vocabulary: R4:third_country -> R4, state:CA -> CA."""
    return {r.split(":")[1] if r.startswith("state:") else r.split(":")[0] for r in refs}


@pytest.mark.parametrize("row", dev_rows(), ids=lambda r: r["id"])
def test_dev_last_turn_matches_gold(row):
    gold = row["gold"][-1]
    facts = row["facts"]
    a = assess(Profile(**facts["profile"]), [Line(**line) for line in facts["basket"]])

    assert a.outcome == gold["outcome"]
    assert a.kind == gold["bottom_line"]["kind"]
    gold_owe = gold["bottom_line"].get("owe_usd")
    assert (None if a.owe_usd is None else str(a.owe_usd)) == gold_owe

    got = {f.name: Decimal(f.value) for f in a.figures}
    want = {f["name"]: Decimal(f["value"]) for f in gold.get("figures", [])}
    assert got == want

    want_notes = set(gold.get("notes_required", []))
    assert set(a.notes) == want_notes

    want_claims = {c["claim"].split()[0] for c in gold.get("citations", [])}
    if gold["outcome"] == "answered":
        assert refs_as_claims(a.rule_refs) == want_claims
