"""The rule and rate tables (pack/rules/): they load, every row cites real clause ids, and the
rates reproduce the worked examples in docs/regulatory-checks.md."""

import json
from decimal import ROUND_HALF_UP, Decimal

import pytest
import yaml

from customs.config import PROJECT_ROOT

RULES = PROJECT_ROOT / "pack" / "rules"
DOCS = PROJECT_ROOT / "data" / "chunks" / "documents.jsonl"


def load(name: str) -> dict:
    return yaml.safe_load((RULES / name).read_text(encoding="utf-8"))


def _strings(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in _strings(v)]
    return []


def all_cites(node) -> list[str]:
    """Every clause id under any `cites` key (a list, or a dict of lists)."""
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            out += _strings(v) if k == "cites" else all_cites(v)
    elif isinstance(node, list):
        for v in node:
            out += all_cites(v)
    return out


TABLES = [
    "rules.yaml",
    "rates.yaml",
    "units.yaml",
    "countries.yaml",
    "brands.yaml",
    "states.yaml",
    "facts.yaml",
]


@pytest.mark.parametrize("name", TABLES)
def test_tables_load(name):
    assert load(name)


def test_rules_are_r1_to_r12_with_status_and_cites():
    rules = load("rules.yaml")["rules"]
    assert [r["id"] for r in rules] == [f"R{i}" for i in range(1, 13)]
    for r in rules:
        assert r["status"] in {"proposed", "signed_off"}
        assert all_cites(r), f"{r['id']} cites nothing"


def test_every_cited_clause_exists_in_the_corpus():
    if not DOCS.exists():
        pytest.skip("corpus not built here (CI): run customs.ingest.build_chunks")
    ids = {json.loads(line)["doc_id"] for line in DOCS.open(encoding="utf-8")}
    missing = {}
    for name in TABLES:
        bad = [c for c in all_cites(load(name)) if c not in ids]
        if bad:
            missing[name] = bad
    assert not missing, missing


def _cents(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rate(cls: str) -> Decimal:
    for row in load("rates.yaml")["excise_alcohol"]:
        if row["class"] == cls:
            return Decimal(str(row["rate"]))
    raise KeyError(cls)


def test_rates_reproduce_example_1_wine_from_italy():
    units = load("units.yaml")
    gal = Decimal(str(units["litres_per_us_gallon"]))
    excess_l = Decimal(2)  # 4 x 750 ml = 3 L, 1 L exempt
    duty = _cents(Decimal(str(load("rates.yaml")["duty"]["flat_rate"]["rate"])) * Decimal(80))
    excise = _cents(excess_l / gal * _rate("still_wine_le_16"))
    assert (duty, excise, duty + excise) == (Decimal("2.40"), Decimal("0.57"), Decimal("2.97"))


def test_rates_reproduce_whole_bottle_spirits_excise():
    units = load("units.yaml")
    gal = Decimal(str(units["litres_per_us_gallon"]))
    proof = Decimal(40) * units["proof_per_abv_percent"]
    proof_gallons = Decimal("0.75") / gal * proof / 100
    assert _cents(proof_gallons * _rate("distilled_spirits")) == Decimal("2.14")


def test_signed_off_and_no_pending_decisions():
    for name in TABLES:
        text = (RULES / name).read_text(encoding="utf-8")
        assert "pending_decision" not in text, name
    assert all(r["status"] == "signed_off" for r in load("rules.yaml")["rules"])
    for name in ("brands.yaml", "states.yaml", "facts.yaml"):
        assert load(name)["status"] == "signed_off", name


def test_decided_parameters():
    rules = {r["id"]: r for r in load("rules.yaml")["rules"]}
    assert rules["R2"]["params"]["beneficiary_list"] == "cbp_types_of_exemptions_page"
    assert rules["R3"]["params"]["tobacco_min_age"] == 21
    assert rules["R7"]["params"]["fta_free"] is True
    assert rules["R10"]["params"]["flag_litres_per_traveller"] == 12
    assert rules["R12"]["params"]["handling"] == "ask_once_then_treat_as_possibly_cuban"
    assert set(load("rules.yaml")["scope_notes"]) >= {"family_groups", "russian_origin_alcohol"}
