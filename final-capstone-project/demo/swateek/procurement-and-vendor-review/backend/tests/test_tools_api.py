"""Domain tools reproduce the frozen gold; the API exposes tools without consequential actions."""

import json

import pytest
from fastapi.testclient import TestClient

from copilot.answer import resolve_handles
from copilot.config import PROJECT_ROOT, get_settings
from copilot.domains.loader import load_domain
from copilot.retrieval.hybrid import rrf
from copilot.tools.registry import Toolbox

CASES = PROJECT_ROOT / "domains" / "procurement" / "data" / "bid_cases"


@pytest.fixture(scope="module")
def toolbox():
    s = get_settings()
    return Toolbox(s, load_domain(s.domain_dir))


@pytest.mark.parametrize(
    "case_dir", sorted(p for p in CASES.iterdir() if p.is_dir()), ids=lambda p: p.name
)
def test_score_bids_reproduces_frozen_gold(toolbox, case_dir):
    gold = json.loads((case_dir / "gold_scores.json").read_text())
    out = toolbox.tools["score_bids"].call({"case_id": case_dir.name})
    if gold.get("refuse"):
        assert out["refusal_rule"] == "R6_no_requirement_sheet"
        return
    got = {(r["bidder"], r["requirement_id"]): r for r in out["rows"]}
    assert len(got) == len(gold["rows"])
    for g in gold["rows"]:
        r = got[(g["bidder"], g["requirement_id"])]
        assert r["score"] == g["score"], (g["bidder"], g["requirement_id"])
        assert (r["gap"] is None) == (g["gap"] is None), (g["bidder"], g["requirement_id"])
        if g["quoted_evidence"]:
            assert r["quoted_evidence"] == g["quoted_evidence"]
    gb = {b["bidder"]: b for b in gold["bidders"]}
    for b in out["bidders"]:
        assert b["status"] == gb[b["bidder"]]["status"]
        assert b["technical_total"] == gb[b["bidder"]]["technical_total"]
        assert b["quoted_price_inr"] == gb[b["bidder"]]["quoted_price_inr"]
        assert b["screening"]["possible_matches"] == sorted(
            gb[b["bidder"]]["screening"]["possible_matches"]
        )
        assert (
            b["screening"]["history_versions"] == gb[b["bidder"]]["screening"]["history_versions"]
        )
    assert out["ranking_eligible"] == gold["ranking_eligible"]
    assert [w["bidder"] for w in out["withheld_bidders"]] == [
        w["bidder"] for w in gold["withheld_bidders"]
    ]
    assert out["is_draft"] is True


def test_tools_return_typed_errors_not_exceptions(toolbox):
    assert (
        toolbox.tools["score_bids"].call({"case_id": "../../etc"})["error"] == "invalid arguments"
    )
    assert "No bid case" in toolbox.tools["score_bids"].call({"case_id": "case_999"})["error"]
    assert toolbox.tools["screen_vendor"].call({})["retryable"] is True


def test_screen_vendor_wording(toolbox):
    absent = toolbox.tools["screen_vendor"].call({"name": "Northwind Computing Pvt Ltd"})
    assert absent["status"] == "not_present"
    assert "not a finding that the firm is eligible" in absent["statement"]
    present = toolbox.tools["screen_vendor"].call({"name": "Prama Hikvision India Pvt Ltd"})
    assert "as of 2024-09-03" in present["statement"]


def test_resolve_handles_maps_and_drops_invalid():
    r = resolve_handles(
        "The limit is Rs 50,000 [1]. Footnote copy [16]. Not cited sentence here.",
        ["gfr_2017:R154", "goods_manual_2024:4.17.2"],
    )
    assert r["answer"].startswith("The limit is Rs 50,000 [gfr_2017:R154].")
    assert r["citations"] == ["gfr_2017:R154"]
    assert r["invalid_handles"] == ["[16]"]
    assert r["uncited_sentences"] == ["Not cited sentence here."]  # <4-word fragments ignored


def test_rrf_prefers_items_ranked_by_both():
    fused = rrf({"bm25": ["a", "b", "c"], "dense": ["b", "d", "a"]})
    assert [c for c, _, _ in fused][:2] == ["b", "a"]


def test_api_has_no_consequential_routes():
    from copilot.api.app import app

    paths = {r.path for r in app.routes}
    for word in ("award", "debar", "order", "approve", "blacklist"):
        assert not any(word in p for p in paths), word
    with TestClient(app) as client:
        d = client.get("/domain").json()
        assert d["ui_modes"] == ["policy", "vendor", "bid"]
        r = client.post("/tools/score_bids", json={"case_id": "case_001"}).json()
        assert r["is_draft"] is True and r["result"]["ranking_eligible"] == ["B1", "B2", "B3"]
        assert client.post("/tools/award", json={}).status_code == 404
        assert len(client.get("/listings/bid-cases").json()) == 10
