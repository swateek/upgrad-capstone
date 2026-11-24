from pathlib import Path

import yaml

from copilot.config import PROJECT_ROOT
from copilot.domains.loader import load_domain
from copilot.domains.manifest import LOCK_NAME, load_exclusions, load_lock, load_manifest

PROCUREMENT = PROJECT_ROOT / "domains" / "procurement"


def test_procurement_domain_loads():
    cfg = load_domain(PROCUREMENT)
    assert cfg.name == "procurement"
    assert cfg.ui_modes == ["policy", "vendor", "bid"]
    assert cfg.corpus.default_chunker in cfg.corpus.chunkers


def test_manifest_valid_and_english_only():
    m = load_manifest(PROCUREMENT / "corpus" / "manifest.yaml")
    assert m.domain == "procurement"
    assert all(s.language == "en" for s in m.sources)
    assert {"policy", "screening"} <= {s.store for s in m.sources}


def test_no_manifest_url_is_excluded():
    m = load_manifest(PROCUREMENT / "corpus" / "manifest.yaml")
    ex = load_exclusions(PROCUREMENT / "corpus" / "exclusions.yaml")
    for s in m.sources:
        for url in [s.url, *s.alt_urls]:
            assert ex.match(url) is None, f"{s.id} -> {url}"


def test_exclusions_catch_superseded_manuals():
    ex = load_exclusions(PROCUREMENT / "corpus" / "exclusions.yaml")
    url = (
        "https://doe.gov.in/files/manuals_documents/"
        "Manual_for_Procurement_of_Consultancy_%26_Other_Services_Updated%20June%2C%202022_1.pdf"
    )
    assert ex.match(url) is not None
    assert ex.match("https://democppp.nic.in/anything") is not None


def test_lock_covers_every_manifest_source():
    m = load_manifest(PROCUREMENT / "corpus" / "manifest.yaml")
    lock = load_lock(PROCUREMENT / "corpus" / LOCK_NAME)
    assert lock is not None
    assert {s.id for s in m.sources} == set(lock.files)
    assert all(len(e.sha256) == 64 for e in lock.files.values())


def test_refusals_cover_the_six_rules():
    data = yaml.safe_load((PROCUREMENT / "refusals.yaml").read_text())
    assert len(data["rules"]) == 6


def test_core_does_not_name_the_procurement_domain():
    core = Path(__file__).resolve().parents[1] / "src" / "copilot"
    banned = ("procurement", "gem_", "gfr", "screen_vendor", "score_bids")
    for py in core.rglob("*.py"):
        text = py.read_text().lower()
        for word in banned:
            assert word not in text, f"{py.name} mentions '{word}'"
