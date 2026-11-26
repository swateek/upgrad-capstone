"""Offline tests for data/rag-corpus/fetch_corpus.py parsers (no network: raw bytes are faked)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PATH = Path(__file__).parents[1] / "data" / "rag-corpus" / "fetch_corpus.py"
spec = importlib.util.spec_from_file_location("fetch_corpus", PATH)
fc = importlib.util.module_from_spec(spec)
sys.modules["fetch_corpus"] = fc  # dataclasses need the module registered
spec.loader.exec_module(fc)

RAW = {
    "file": "x.gz",
    "url": "u",
    "sha256": "0" * 64,
    "fetched_at": "2026-11-21T00:00:00Z",
}


@pytest.fixture
def fake_raw(monkeypatch):
    pages: dict[str, bytes] = {}

    def fetch_raw(source_id, key, url, ext):
        for k, v in pages.items():
            if k in key or k in url:
                return v, RAW
        raise AssertionError(f"unexpected fetch {key} {url}")

    monkeypatch.setattr(fc, "fetch_raw", fetch_raw)
    monkeypatch.setattr(fc, "ecfr_latest_date", lambda t: "2026-11-19")
    return pages


ECFR = b"""<DIV5 N="148" TYPE="PART"><HEAD>PART 148</HEAD>
<DIV6 N="D" TYPE="SUBPART"><HEAD>Subpart D\xe2\x80\x94Exemptions for Returning Residents</HEAD>
<DIV8 N="148.33" TYPE="SECTION"><HEAD>\xc2\xa7 148.33 Articles acquired abroad.</HEAD>
<P>(a) <I>Exemption.</I> Articles acquired abroad by a returning resident.</P>
<P>(d) Alcoholic beverages: not more than 1 liter.</P><CITA>[T.D. 00-00]</CITA></DIV8>
<DIV8 N="148.40" TYPE="SECTION"><HEAD>\xc2\xa7 148.40 [Reserved]</HEAD></DIV8>
</DIV6>
<DIV6 N="G" TYPE="SUBPART"><HEAD>Subpart G\xe2\x80\x94Crewmembers</HEAD>
<DIV8 N="148.64" TYPE="SECTION"><HEAD>\xc2\xa7 148.64 Exemptions for crewmembers.</HEAD>
<P>(b) 50 cigarettes, 10 cigars, 150 milliliters of alcoholic beverages.</P></DIV8></DIV6></DIV5>"""


def test_ecfr_one_doc_per_section_with_subpart_rules(fake_raw) -> None:
    fake_raw["part-148"] = ECFR
    src = {
        "id": "19cfr148",
        "title_number": 19,
        "part": "148",
        "authority": "primary_regulation",
        "tags": ["cfr"],
        "heading_rules": [
            {"if_any": ["crewmember"], "tags": ["crew"], "authority": "hard_negative"},
            {"if_any": ["returning resident"], "tags": ["returning_resident"]},
        ],
    }
    docs = {d.doc_id: d for d in fc.fetch_ecfr(src)}
    assert set(docs) == {"19cfr148.33", "19cfr148.64"}  # reserved section dropped
    d = docs["19cfr148.33"]
    assert d.citation_id == "19cfr148.33" and d.authority == "primary_regulation"
    assert (
        "returning_resident" in d.tags
        and "1 liter" in d.text
        and "_[T.D. 00-00]_" in d.text
    )
    assert d.source_url == "https://www.ecfr.gov/current/title-19/section-148.33"
    assert (
        docs["19cfr148.64"].authority == "hard_negative"
        and "crew" in docs["19cfr148.64"].tags
    )


USC = b"""<html><body><div id="content">
<h3>&#167;5754. Restriction on importation of previously exported tobacco products</h3>
<h4>(a) Export-labeled tobacco products</h4><p>(1) Tobacco products manufactured in the United States and labeled for exportation may be imported only as provided in section 5704(d).</p>
<h4>(b) Export label</h4><p>For purposes of this section, an article is labeled for export if it bears the mark required under section 5704(b).</p>
<h4>Editorial Notes</h4><h4>Amendments</h4><p>2000 - Pub. L. 106-476 rewrote the section.</p>
</div></body></html>"""


def test_usc_one_doc_per_subsection_without_notes(fake_raw) -> None:
    fake_raw["26usc5754"] = USC
    src = {
        "id": "26usc",
        "title_number": 26,
        "sections": ["5754"],
        "authority": "primary_regulation",
        "tags": [],
    }
    docs = fc.fetch_usc(src)
    assert [d.doc_id for d in docs] == ["26usc5754-a", "26usc5754-b"]
    assert all(d.citation_id == "26usc5754" for d in docs)
    assert not any("Pub. L. 106-476" in d.text for d in docs)


FAQ = b"""<html><body><nav><ul><li><a href="/x">SDN List</a></li></ul></nav><main>
<p><strong><a href="/faqs/topic/1541">Cuba Sanctions</a></strong></p>
<h1>719. Can I purchase Cuban-origin cigars while traveling in Cuba?</h1>
<p>Answer</p><p>Authorized travelers may no longer return to the United States with alcohol and/or tobacco products acquired in Cuba.</p>
<h2>Similar FAQs</h2><p><a href="720">720. Can I purchase ... third country?</a></p></main></body></html>"""


def test_ofac_faq_keeps_question_and_answer_only(fake_raw) -> None:
    fake_raw["faq-719"] = FAQ
    src = {
        "id": "ofac",
        "ids": [719],
        "authority": "agency_guidance",
        "tags": ["ofac"],
        "heading_rules": [{"if_any": ["cigar"], "tags": ["tobacco"]}],
    }
    (d,) = fc.fetch_ofac_faqs(src)
    assert d.doc_id == d.citation_id == "ofac-faq-719"
    assert (
        "no longer return" in d.text and "Similar" not in d.text and "720" not in d.text
    )
    assert "tobacco" in d.tags and d.extra["topic"] == "Cuba Sanctions"


PAGE = b"""<html><body><header>site header</header><main>
<h1>Prohibited and Restricted Items</h1><p>Intro paragraph about items that need care when entering the United States.</p>
<h2>Alcoholic Beverages</h2><p>In addition to U.S. laws, travelers must follow the laws of the state where they arrive.</p>
<h2>Pets</h2><p>Pets taken out of the country and returned are subject to the same requirements as new arrivals.</p>
<p>Last Modified: Jan 1, 2026</p><h2>Footer stuff</h2><p>should be cut by the end marker before this point</p>
</main></body></html>"""


def test_html_split_by_h2_marks_off_topic_sections_as_hard_negatives(fake_raw) -> None:
    fake_raw["main"] = PAGE
    src = {
        "id": "cbp_pr",
        "title": "CBP - Prohibited",
        "url": "https://cbp.gov/p",
        "citation_id": "cbp-pr",
        "split": "h2",
        "start": r"^#\s+",
        "end": [r"^\**Last Modified"],
        "authority": "agency_guidance",
        "tags": ["cbp"],
        "off_topic_unless": ["alcohol", "prohibited and restricted"],
    }
    docs = {d.doc_id: d for d in fc.fetch_html(src)}
    assert set(docs) == {
        "cbp-pr--prohibited-and-restricted-items",
        "cbp-pr--alcoholic-beverages",
        "cbp-pr--pets",
    }
    assert docs["cbp-pr--alcoholic-beverages"].authority == "agency_guidance"
    assert (
        docs["cbp-pr--pets"].authority == "hard_negative"
        and "off_topic" in docs["cbp-pr--pets"].tags
    )
    assert all(d.citation_id == "cbp-pr" for d in docs.values())
    assert not any("Footer" in d.text or "site header" in d.text for d in docs.values())


def test_html_to_markdown_drops_link_only_navigation() -> None:
    md = fc.html_to_markdown(
        b"<main><ul><li><a href='/a'>Travel</a></li></ul><p>Real text <a href='/b'>here</a>.</p></main>"
    )
    assert "Travel" not in md and "Real text here." in md
