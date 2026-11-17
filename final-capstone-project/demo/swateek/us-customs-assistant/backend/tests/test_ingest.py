"""Corpus ingest, offline: manifest consistency, each parser on small fixtures, the downloader's
format checks and lock logic (mock transport), and the chunk helpers."""

import json

import httpx
import pytest
import yaml

from customs.config import PROJECT_ROOT
from customs.ingest import download as dl
from customs.ingest.build_chunks import (
    _section_batches,
    _section_citation,
    is_empty,
    load_synthetic,
    split_parts,
)
from customs.ingest.manifest import (
    LOCK_NAME,
    Source,
    SplitSpec,
    load_exclusions,
    load_lock,
    load_manifest,
    load_splitting,
)
from customs.ingest.parsers import (
    LetterSequence,
    blocks_from_pages,
    parse_ecfr_xml,
    parse_html_sections,
    parse_hts_json,
    parse_ofac_faqs,
    parse_usc_html,
)

CORPUS = PROJECT_ROOT / "pack" / "corpus"


def _src(**kw) -> Source:
    base = {
        "id": "t",
        "title": "Test source",
        "publisher": "test",
        "url": "https://example.gov/x",
        "source_page": "https://example.gov/",
        "format": "html",
        "parser": "html_sections",
        "topic": "exemptions",
        "edition": "test",
        "edition_date": None,
    }
    return Source(**{**base, **kw})


# --- manifest ---------------------------------------------------------------------------------


def test_manifest_splitting_lock_and_exclusions_agree():
    manifest = load_manifest(CORPUS / "manifest.yaml")
    specs = load_splitting(CORPUS / "splitting.yaml")
    exclusions = load_exclusions(CORPUS / "exclusions.yaml")
    lock = load_lock(CORPUS / LOCK_NAME)
    ids = {s.id for s in manifest.sources}
    assert ids <= set(specs), f"no splitting rule for {ids - set(specs)}"
    assert all(exclusions.match(s.url) is None for s in manifest.sources)
    assert lock is not None and set(lock.files) == ids
    assert all(s.language == "en" for s in manifest.sources)
    # eCFR sources are pinned to a date, never the daily-changing "current" pages
    assert all("/versioner/v1/full/" in s.url for s in manifest.sources if s.parser == "ecfr_xml")


def test_exclusions_catch_the_info_center():
    ex = load_exclusions(CORPUS / "exclusions.yaml")
    assert ex.match("https://help.cbp.gov/s/article/Article-1184?language=en_US")
    assert ex.match("https://www.ecfr.gov/current/title-19/part-148")


def test_synthetic_fixtures_are_marked():
    fixtures = load_synthetic(CORPUS / "synthetic", "Synthetic fixture")
    assert len(fixtures) >= 3
    for meta, docs in fixtures:
        assert meta["synthetic"] is True and meta["id"].startswith("synthetic_")
        assert all(d.citation.startswith("Synthetic fixture") for d in docs)


# --- parsers ----------------------------------------------------------------------------------

ECFR = b"""<?xml version="1.0" encoding="UTF-8"?>
<DIV5 N="148" TYPE="PART">
<DIV8 N="148.33" TYPE="SECTION">
<HEAD>&#xA7; 148.33 Articles acquired abroad.</HEAD>
<P>(a) <I>Exemption.</I> Each returning resident is entitled to bring in free of duty.</P>
<P>(1) $800, and provided that the articles accompany the returning resident;</P>
<P>(b) <I>Highest rate.</I> Applied to articles subject to the highest rates of duty.</P>
<P>(c) Gifts.</P><P>(d) Tobacco.</P><P>(e) E.</P><P>(f) F.</P><P>(g) G.</P><P>(h) H.</P>
<P>(i) Letter i, right after (h).</P>
<P>(i) Roman i inside (i)? No: the next letter is j, so this stays with (i).</P>
<CITA>[T.D. 94-1]</CITA>
</DIV8>
<DIV8 N="148.34" TYPE="SECTION"><HEAD>&#xA7; 148.34 [Reserved]</HEAD></DIV8>
<DIV8 N="148.35" TYPE="SECTION"><HEAD>&#xA7; 148.35 Plain section.</HEAD><P>No letters here.</P></DIV8>
</DIV5>"""


def test_ecfr_paragraph_units_and_letter_sequence():
    docs = parse_ecfr_xml(
        _src(format="xml", parser="ecfr_xml"), SplitSpec(citation_prefix="19 CFR"), ECFR
    )
    ids = [d.unit_id for d in docs]
    assert ids[:3] == ["148.33(a)", "148.33(b)", "148.33(c)"]
    assert "148.33(i)" in ids and ids.count("148.33(i)") == 1
    assert "148.34" not in ids  # reserved section skipped
    assert "148.35" in ids
    a = docs[0]
    assert a.citation == "19 CFR 148.33(a)" and a.section_id == "148.33"
    assert "$800" in a.text  # (1) stays with (a)
    assert a.title.endswith("— Exemption")
    assert all("T.D. 94-1" not in d.text for d in docs)  # source citations dropped


def test_letter_sequence_roman_i():
    seq = LetterSequence()
    assert seq.accept("(a) x") == "a"
    assert seq.accept("(i) roman") is None  # expected (b)
    assert seq.accept("(b) y") == "b"


USC = b"""<html><body><h3 class="section-head">&#167;5001. Imposition, rate, and attachment of tax</h3>
<!-- field-start:statute -->
<h4 class="subsection-head">(a) Rate of tax</h4>
<h4 class="paragraph-head">(1) General</h4>
<p class="statutory-body-1em">A tax at the rate of $13.50 on each proof gallon.</p>
<h4 class="subsection-head">(b) Attachment of tax</h4>
<p class="statutory-body">The tax attaches when the spirits are produced.</p>
<!-- field-end:statute -->
<h4 class="note-head">Amendments</h4><p>Not statute text.</p>
</body></html>"""


def test_usc_subsections():
    docs = parse_usc_html(_src(parser="usc_html"), SplitSpec(citation_prefix="26 USC"), USC)
    assert [d.citation for d in docs] == ["26 USC 5001(a)", "26 USC 5001(b)"]
    assert "$13.50" in docs[0].text and "Amendments" not in " ".join(d.text for d in docs)


PAGE = b"""<!doctype html><html><body><nav>Menu Home About</nav>
<main><h1>Customs Duty Information</h1>
<p>Intro paragraph that explains the page and is long enough to stand alone as text.</p>
<h2>Alcoholic Beverages</h2><p>One liter of alcoholic beverages may be included.</p>
<ul><li>You are 21 years old.</li><li>It is for your own use.</li></ul>
<h2>Rates</h2><table><tr><th>Class</th><th>Rate</th></tr><tr><td>Wine</td><td>$1.07</td></tr><tr><td>Sparkling wine</td><td>$3.40</td></tr></table>
<h2>Contact</h2><p>Call us at the office between nine and five on weekdays please.</p>
<p>Last Modified: Nov 1, 2026</p>
</main><footer>Footer links</footer></body></html>"""


def test_html_sections_blocks_lists_tables_and_drops():
    spec = SplitSpec(citation_prefix="CBP, Customs Duty Information", drop_headings=["^contact$"])
    docs = parse_html_sections(_src(), spec, PAGE)
    assert [d.unit_id for d in docs] == ["overview", "alcoholic-beverages", "rates"]
    alc = docs[1]
    assert alc.citation == "CBP, Customs Duty Information — Alcoholic Beverages"
    assert "- You are 21 years old." in alc.text
    assert "Wine | $1.07" in docs[2].text
    assert all("Menu" not in d.text and "Last Modified" not in d.text for d in docs)


def test_ofac_faqs_one_document_each():
    items = "".join(
        f"<h3>{700 + i}. Question number {i}?</h3><p>Answer {i}.</p>" for i in range(12)
    )
    raw = f"<html><body><main><h1>Cuba Sanctions</h1>{items}</main></body></html>".encode()
    docs = parse_ofac_faqs(_src(parser="ofac_faqs"), SplitSpec(citation_prefix="OFAC FAQ"), raw)
    assert len(docs) == 12
    assert docs[0].citation == "OFAC FAQ 700" and docs[0].unit_id == "faq-700"
    assert docs[0].text.startswith("Q: Question number 0?") and "Answer 0." in docs[0].text


def test_hts_rows_group_by_subheading_with_context():
    rows = [
        {"htsno": "", "indent": "0", "description": "Articles of a returning resident:"},
        {"htsno": "9804.00.65", "indent": "1", "description": "Other", "general": "Free"},
        {"htsno": "9804.00.65.00", "indent": "2", "description": "Stat row"},
        {"htsno": "9816.00.20", "indent": "1", "description": "Flat rate", "general": "3%"},
    ]
    spec = SplitSpec(citation_prefix="HTSUS", hts_prefixes=["9804."])
    docs = parse_hts_json(_src(format="json", parser="hts_json"), spec, json.dumps(rows).encode())
    assert [d.unit_id for d in docs] == ["9804.00.65"]
    assert "Articles of a returning resident" in docs[0].text
    assert "General: Free" in docs[0].text and "Stat row" in docs[0].text


def test_pdf_blocks_contexts_units_and_drops():
    spec = SplitSpec(
        citation_prefix="HTSUS",
        pages=[[3, 3], [23, 23]],
        page_contexts=["General Note 3", "General Note 6"],
        context_pattern=r"^(?P<id>7)\.\s+Products of Countries Designated",
        context_template="General Note {id}",
        unit_pattern=r"^\((?P<id>[a-z])\)\s",
        letter_sequence=True,
        drop_patterns=["^Harmonized Tariff Schedule"],
    )
    pages = [
        (
            3,
            [
                "(a) Rate of Duty Column 1.",
                "(i) Except as provided",
                "Harmonized Tariff Schedule x",
            ],
        ),
        (
            23,
            [
                "(a) civil aircraft",
                "7. Products of Countries Designated as Beneficiary",
                "(a) The following countries",
                "(b) (i) Unless otherwise excluded",
            ],
        ),
    ]
    docs = blocks_from_pages(_src(format="pdf", parser="pdf_blocks"), spec, pages, spec.pages)
    cites = [d.citation for d in docs]
    assert cites == [
        "HTSUS General Note 3(a)",
        "HTSUS General Note 6(a)",
        "HTSUS General Note 7",
        "HTSUS General Note 7(a)",
        "HTSUS General Note 7(b)",
    ]
    assert "(i) Except as provided" in docs[0].text
    assert all("Harmonized Tariff" not in d.text for d in docs)


# --- chunk helpers ------------------------------------------------------------------------------


def test_is_empty_drops_reserved_and_heading_only():
    assert is_empty("(b) [Reserved]")
    assert is_empty("[REDACTED-PHONE]")
    assert is_empty("Application Procedures")
    assert not is_empty("(c) Gifts may be included in the exemption.")


def test_split_parts_respects_limit():
    count = lambda t: len(t.split())
    text = "\n".join(["word " * 30] * 5)
    parts = split_parts(text, count, 70)
    assert len(parts) > 1 and all(count(p) <= 70 for p in parts)
    long_line = "w " * 200
    assert all(count(p) <= 50 for p in split_parts(long_line, count, 50))


def test_section_batches_and_citation():
    class D:
        def __init__(self, n, c):
            self.n_tokens, self.citation = n, c

    docs = [D(700, "19 CFR 148.33(a)"), D(600, "19 CFR 148.33(b)"), D(100, "19 CFR 148.33(c)")]
    assert [len(b) for b in _section_batches(docs)] == [1, 2]
    assert _section_citation(docs) == "19 CFR 148.33"


# --- downloader ----------------------------------------------------------------------------------


@pytest.fixture
def corpus_tmp(tmp_path, monkeypatch):
    cdir = tmp_path / "corpus"
    cdir.mkdir()
    sources = [
        {
            "id": "page",
            "title": "Page",
            "publisher": "test",
            "url": "https://example.gov/page",
            "source_page": "https://example.gov/",
            "format": "html",
            "parser": "html_sections",
            "topic": "exemptions",
            "edition": "live",
            "edition_date": None,
        },
        {
            "id": "doc",
            "title": "Doc",
            "publisher": "test",
            "url": "https://example.gov/doc.pdf",
            "source_page": "https://example.gov/",
            "format": "pdf",
            "parser": "pdf_blocks",
            "topic": "state",
            "edition": "x",
            "edition_date": None,
        },
    ]
    (cdir / "manifest.yaml").write_text(
        yaml.safe_dump({"checked_on": "2026-11-17", "sources": sources})
    )
    (cdir / "exclusions.yaml").write_text(yaml.safe_dump({"url_patterns": ["*help.cbp.gov*"]}))
    monkeypatch.setattr(dl, "corpus_dir", lambda: cdir)
    monkeypatch.setattr(dl, "raw_dir", lambda: tmp_path / "raw")
    monkeypatch.setattr(dl, "PAUSE_S", 0)
    return cdir


def _client(bodies):
    def handler(request):
        return httpx.Response(200, content=bodies[str(request.url)])

    return httpx.Client(transport=httpx.MockTransport(handler))


HTML_V1 = (
    b"<!doctype html><html><body><main><p>" + b"Rule text one. " * 20 + b"</p></main></body></html>"
)


def test_freeze_then_verify_with_text_hash(corpus_tmp):
    bodies = {"https://example.gov/page": HTML_V1, "https://example.gov/doc.pdf": b"%PDF-1.4 x"}
    assert dl.run(freeze=True, client=_client(bodies)) == 0
    lock = load_lock(corpus_tmp / LOCK_NAME)
    assert set(lock.files) == {"page", "doc"}
    # markup outside the main content changes: raw hash differs, text hash holds -> passes
    bodies["https://example.gov/page"] = HTML_V1.replace(b"<body>", b"<body><nav>new banner</nav>")
    assert dl.run(freeze=False, client=_client(bodies)) == 0
    # the rule text changes -> verification fails
    bodies["https://example.gov/page"] = HTML_V1.replace(b"one", b"two")
    assert dl.run(freeze=False, client=_client(bodies)) == 1


def test_wrong_format_is_refused_and_lock_not_written(corpus_tmp):
    bodies = {"https://example.gov/page": HTML_V1, "https://example.gov/doc.pdf": b"<html>oops"}
    assert dl.run(freeze=True, client=_client(bodies)) == 1
    assert not (corpus_tmp / LOCK_NAME).exists()
