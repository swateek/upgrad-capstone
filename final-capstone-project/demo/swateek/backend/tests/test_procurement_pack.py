"""Procurement domain-pack data: screening matching rules, bid cases, eval-set integrity."""

import csv
import json
import subprocess
import sys
from collections import Counter

import pytest

from copilot.config import PROJECT_ROOT

PACK = PROJECT_ROOT / "domains" / "procurement"
sys.path.insert(0, str(PACK))
from screening import match, normalize

CHUNKS = PROJECT_ROOT / "data" / "processed" / "procurement" / "chunks" / "by_rule.jsonl"


@pytest.fixture(scope="module")
def gem_rows():
    with (PACK / "data" / "screening" / "gem_delisted_sellers.csv").open() as fh:
        return list(csv.DictReader(fh))


def test_normalize_strips_legal_forms_and_punctuation():
    assert normalize("Prama Hikvision (India) Pvt. Ltd.") == "PRAMA HIKVISION INDIA"
    assert (
        normalize("LENOVO GLOBAL TECHNOLOGY (INDIA) PRIVATELIMITED")
        == "LENOVO GLOBAL TECHNOLOGY INDIA"
    )
    assert normalize("Domino Printech India LLP") == "DOMINO PRINTECH INDIA"


def test_latest_version_only_decides_presence(gem_rows):
    assert sum(r["in_latest_version"] == "true" for r in gem_rows) == 130
    assert match("Prama Hikvision India Pvt Ltd", gem_rows)["status"] == "present"
    lava = match("Lava International Ltd", gem_rows)
    assert lava["status"] == "not_present" and lava["history_versions"] == ["2024-01-31"]


def test_possible_match_never_becomes_present(gem_rows):
    r = match("Dahua Technologies India Pvt Ltd", gem_rows)
    assert r["status"] == "not_present"
    assert {p["listed_name"] for p in r["possible_matches"]} == {"DAHUA", "DAHUA TECHNOLOGY INDIA"}
    assert match("Prama Vision India Pvt Ltd", gem_rows)["possible_matches"] == []


def test_bid_cases_validate():
    script = PACK / "pipelines" / "validate_bid_cases.py"
    res = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stdout + res.stderr
    assert res.stdout.count("ok ") == 10


def test_eval_set_shape():
    qs = [json.loads(x) for x in (PACK / "eval" / "queries.jsonl").read_text().splitlines()]
    assert 60 <= len(qs) <= 100
    assert len({q["id"] for q in qs}) == len(qs)
    assert Counter(q["job"] for q in qs) == {"policy": 25, "screening": 20, "bid": 15}
    refusal_rules = {q["gold"].get("refusal_rule") for q in qs if q["must_refuse"]}
    # the brief's mandatory safety set
    assert {
        "R2_instruction_in_data",
        "R3_unindexed_edition",
        "R1_consequential_action",
        "R4_absence_is_not_eligibility",
    } <= refusal_rules
    dev = {json.loads(x)["query"] for x in (PACK / "eval" / "dev.jsonl").read_text().splitlines()}
    assert not dev & {q["query"] for q in qs}, "dev questions must not leak into the frozen set"


@pytest.mark.skipif(not CHUNKS.exists(), reason="run copilot.ingest.build_chunks first")
def test_every_gold_citation_exists_in_the_index():
    known = {json.loads(x)["citation"] for x in CHUNKS.read_text().splitlines()}
    qs = [json.loads(x) for x in (PACK / "eval" / "queries.jsonl").read_text().splitlines()]
    labels = [
        json.loads(x) for x in (PACK / "eval" / "retrieval_labels.jsonl").read_text().splitlines()
    ]
    cited = [
        c
        for q in qs
        for k in ("rule_ids", "also_accept", "redirect_rule_ids")
        for c in q["gold"].get(k, [])
    ]
    cited += [c for lb in labels for c in lb["gold_rule_ids"]]
    assert set(cited) <= known, sorted(set(cited) - known)
    assert len(labels) == 15
