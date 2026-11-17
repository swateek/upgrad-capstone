from copilot.ingest.pdf_text import Line
from copilot.ingest.pii import scrub
from copilot.ingest.split import HeadingPattern, SplitSpec, split_sections, to_pieces
from copilot.retrieval.bm25 import BM25Index, tokenize

MANUAL = HeadingPattern(
    regex=r"^(?P<num>\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\.?(?:\s+(?P<title>\S.*))?$"
)
ANNEX = HeadingPattern(regex=r"^(?P<num>Annexure\s*\d+)\b", id_template="{slug}", reset=True)


def page(n, *texts, size=10.0):
    return [Line(n, t, size) for t in texts]


def test_ordered_headings_reject_toc_and_numbers_in_text():
    pages = [
        page(
            1,
            "4.1 Scope",
            "This applies to goods.",
            "4.25 lakh is not a heading",
            "4.2 Methods",
            "Methods are listed here.",
            "1.1 stray restart rejected",
        ),
    ]
    secs = split_sections(pages, SplitSpec(patterns=[MANUAL]))
    assert [s.rule_id for s in secs] == ["4.1", "4.2"]
    assert any("4.25 lakh" in b for b in secs[0].body)


def test_annexure_resets_numbering_and_namespaces_ids():
    pages = [
        page(1, "1.1 Intro", "Body text here for the intro section."),
        page(2, "Annexure 3", "Form text.", "1.1 Item one", "Annex body text for item one."),
    ]
    spec = SplitSpec(patterns=[MANUAL, ANNEX], annex_start_page=2)
    assert [s.rule_id for s in split_sections(pages, spec)] == [
        "1.1",
        "annexure-3",
        "annexure-3/1.1",
    ]


def test_annexure_mention_before_annex_pages_is_body():
    pages = [page(1, "1.1 Intro", "Annexure 5 of this manual gives the form.")]
    spec = SplitSpec(patterns=[MANUAL, ANNEX], annex_start_page=10)
    secs = split_sections(pages, spec)
    assert [s.rule_id for s in secs] == ["1.1"]


def test_exclude_annexures_drops_annex_pages():
    pages = [page(1, "1.1 Intro", "Body."), page(2, "Annexure 1", "Form.")]
    spec = SplitSpec(patterns=[MANUAL, ANNEX], annex_start_page=2, exclude_annexures=True)
    assert [s.rule_id for s in split_sections(pages, spec)] == ["1.1"]


def test_bare_heading_folds_but_one_line_sentence_is_kept():
    pages = [
        page(
            1,
            "7.6 Procurement Planning",
            "7.6.1 Plan early",
            "Plans are made yearly.",
            "7.6.2 This one-line paragraph is content.",
            "7.6.3 Last",
            "Final body.",
        )
    ]
    secs = split_sections(pages, SplitSpec(patterns=[MANUAL]))
    assert [s.rule_id for s in secs] == ["7.6.1", "7.6.2", "7.6.3"]
    assert secs[0].body[0] == "[7.6 Procurement Planning]"


def test_small_font_footnotes_attach_to_rules_on_that_page():
    rule = HeadingPattern(regex=r"^Rule\s+(?P<num>\d{3})", id_template="R{num}")
    body = [
        Line(1, "Rule 154 Purchase without quotation", 9.3),
        Line(1, "Up to Rs 50,000.", 9.3),
        Line(1, "16 Replace with Rs 2,00,000 for scientific departments", 7.5),
        Line(1, "Rule 155 Purchase Committee", 9.3),
        Line(1, "Above Rs 50,000.", 9.3),
    ]
    secs = split_sections([body], SplitSpec(patterns=[rule], footnote_font_delta=1.0))
    assert [s.rule_id for s in secs] == ["R154", "R155"]
    assert all("Rs 2,00,000" in " ".join(s.notes) for s in secs)
    assert all("Rs 2,00,000" not in " ".join(s.body) for s in secs)


def test_long_sections_split_into_parts_under_budget():
    pages = [page(1, "1.1 Long", *[f"line {i} " + "word " * 20 for i in range(40)])]
    secs = split_sections(pages, SplitSpec(patterns=[MANUAL]))
    pieces = to_pieces(secs, lambda t: len(t.split()), max_tokens=100)
    assert len(pieces) > 1
    assert {p.parts for p in pieces} == {len(pieces)}
    assert all(sum(len(x.split()) + 1 for x in p.text.splitlines()) <= 100 for p in pieces)


def test_pii_scrub():
    text, found = scrub("Mail a.b@example.gov.in, PAN ABCDE1234F, phone 9876543210.")
    assert "[REDACTED-EMAIL]" in text and "[REDACTED-PAN]" in text and "[REDACTED-PHONE]" in text
    assert found == {"EMAIL": 1, "PAN": 1, "PHONE": 1}


def test_bm25_keeps_amounts_and_ranks_relevant_chunk_first():
    assert "50,000" in tokenize("Up to Rs 50,000 on GeM")
    chunks = [
        {
            "chunk_id": "a#1",
            "citation": "a",
            "doc_id": "d",
            "text": "bid security two to five percent",
            "n_tokens": 5,
        },
        {
            "chunk_id": "b#1",
            "citation": "b",
            "doc_id": "d",
            "text": "performance security three to five",
            "n_tokens": 5,
        },
        {
            "chunk_id": "c#1",
            "citation": "c",
            "doc_id": "e",
            "text": "liquidated damages per week",
            "n_tokens": 4,
        },
    ]
    hits = BM25Index(chunks).search("how much bid security", k=2)
    assert hits[0].citation == "a"
    assert BM25Index(chunks).search("security", k=5, doc_ids={"e"}) == [] or all(
        h.citation == "c" for h in BM25Index(chunks).search("security", k=5, doc_ids={"e"})
    )
