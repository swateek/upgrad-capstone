"""Turn each downloaded source into documents: one document = one citable unit (plan §5).

    ecfr_xml       eCFR point-in-time XML: one document per top-level paragraph of a section
                   ("19 CFR 148.33(a)"); a section without lettered paragraphs is one document
    usc_html       govinfo US Code HTML: one document per subsection ("26 USC 5001(a)")
    html_sections  agency and state web pages: one document per heading block in the main content
    ofac_faqs      OFAC FAQ topic page: one document per FAQ ("OFAC FAQ 719")
    hts_json       USITC HTS export rows: one document per 8-digit subheading ("HTSUS 9804.00.65")
    pdf_blocks     PDFs (HTS notes, a state form): blocks started by patterns from splitting.yaml
    markdown       synthetic fixtures (pack/corpus/synthetic/*.md): one document per "## " heading

Downloaded files are data only: parsed, never executed. XML goes through defusedxml.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from defusedxml import ElementTree as SafeET
from pypdf import PdfReader

from customs.ingest.manifest import Source, SplitSpec

SPACES = re.compile(r"\s+")


class ParseError(RuntimeError):
    pass


@dataclass
class Document:
    source_id: str
    unit_id: str  # "148.33(a)", "5001(a)", "faq-719", "9804.00.65", "alcohol"
    citation: str  # human-readable: "19 CFR 148.33(a)"
    section_id: str  # grouping for the whole-section chunker: "148.33", "5001", "faq-719"
    title: str  # heading path shown in the chunk header
    text: str

    @property
    def doc_id(self) -> str:
        """Clause id: what citations, gold labels and rule_refs point to."""
        return f"{self.source_id}:{self.unit_id}"


def norm(text: str) -> str:
    return SPACES.sub(" ", text).strip()


def slug(text: str, limit: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:limit].rstrip("-") or "section"


# --- letters sequence: (a), (b) ... where "(i)" is a letter only right after "(h)" -------------

TOP_LETTER = re.compile(r"^\(([a-z])\)\s*")


class LetterSequence:
    def __init__(self) -> None:
        self.expected = "a"

    def accept(self, text: str) -> str | None:
        m = TOP_LETTER.match(text)
        if not m or m.group(1) != self.expected:
            return None
        self.expected = chr(ord(self.expected) + 1)
        return m.group(1)


# --- eCFR XML ------------------------------------------------------------------------------------

SKIP_ECFR = {"CITA", "SOURCE", "AUTH", "EDNOTE", "SECAUTH"}


def parse_ecfr_xml(src: Source, spec: SplitSpec, raw: bytes) -> list[Document]:
    root = SafeET.fromstring(raw)
    docs: list[Document] = []
    for sec in root.iter("DIV8"):
        if sec.get("TYPE") != "SECTION":
            continue
        num = sec.get("N", "").strip()
        head_el = sec.find("HEAD")
        head = norm("".join(head_el.itertext())) if head_el is not None else num
        title = re.sub(r"^§\s*[\d.a-z]+\s*", "", head).strip() or head
        paras = [
            norm("".join(el.itertext()))
            for el in sec
            if el.tag not in SKIP_ECFR and el.tag != "HEAD"
        ]
        paras = [p for p in paras if p]
        if not paras or (len(paras) == 1 and "[Reserved]" in paras[0]) or "[Reserved]" in head:
            continue
        seq = LetterSequence()
        units: list[tuple[str, list[str]]] = []
        for p in paras:
            letter = seq.accept(p)
            if letter is not None:
                units.append((f"({letter})", [p]))
            elif units:
                units[-1][1].append(p)
            else:
                units.append(("", [p]))  # intro text before (a), or a section without letters
        if len(units) > 1 and units[0][0] == "":  # fold an intro into the first lettered unit
            intro = units.pop(0)
            units[0] = (units[0][0], intro[1] + units[0][1])
        for letter, body in units:
            sub = _paragraph_title(body[0]) if letter else ""
            docs.append(
                Document(
                    source_id=src.id,
                    unit_id=f"{num}{letter}",
                    citation=f"{spec.citation_prefix} {num}{letter}",
                    section_id=num,
                    title=f"§ {num} {title}" + (f" — {sub}" if sub else ""),
                    text="\n".join(body),
                )
            )
    if not docs:
        raise ParseError(f"{src.id}: no sections found")
    return docs


def _paragraph_title(text: str) -> str:
    """eCFR paragraphs often start "(a) <I>Exemption.</I> ..."; keep the short italic title."""
    m = re.match(r"^\([a-z]\)\s*([A-Z][^.]{2,60})\.\s", text)
    return m.group(1) if m else ""


# --- govinfo US Code HTML -----------------------------------------------------------------------

STATUTE = re.compile(r"<!-- field-start:statute -->(.*?)<!-- field-end:statute -->", re.DOTALL)


def parse_usc_html(src: Source, spec: SplitSpec, raw: bytes) -> list[Document]:
    html = raw.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    head = soup.find(class_="section-head")
    if head is None:
        raise ParseError(f"{src.id}: no section-head")
    m = re.match(r"§\s*(\d+[A-Za-z]*)\.\s*(.*)", norm(head.get_text(" ")))
    if not m:
        raise ParseError(f"{src.id}: unexpected section head {head.get_text()[:60]!r}")
    num, title = m.group(1), m.group(2)
    body = STATUTE.search(html)
    if body is None:
        raise ParseError(f"{src.id}: statute text markers missing")
    part = BeautifulSoup(body.group(1), "html.parser")
    units: list[tuple[str, str, list[str]]] = []
    for el in part.find_all(["h4", "p"]):
        text = norm(el.get_text(" "))
        if not text:
            continue
        if el.name == "h4" and "subsection-head" in (el.get("class") or []):
            sm = re.match(r"^\(([a-z])\)\s*(.*)", text)
            units.append((f"({sm.group(1)})" if sm else "", sm.group(2) if sm else text, [text]))
        elif units:
            units[-1][2].append(text)
        else:
            units.append(("", "", [text]))
    docs = [
        Document(
            source_id=src.id,
            unit_id=f"{num}{letter}",
            citation=f"{spec.citation_prefix} {num}{letter}",
            section_id=num,
            title=f"§ {num} {title}" + (f" — {sub}" if sub else ""),
            text="\n".join(lines),
        )
        for letter, sub, lines in units
    ]
    if not docs:
        raise ParseError(f"{src.id}: no statute text")
    return docs


# --- agency and state web pages -----------------------------------------------------------------

DROP_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "button"]
DROP_CLASS = re.compile(
    r"breadcrumb|sidebar|menu|share|social|usa-banner|skip|pager|feedback", re.IGNORECASE
)
LAST_MODIFIED = re.compile(r"^Last Modified:", re.IGNORECASE)


def main_container(soup: BeautifulSoup) -> Tag:
    for sel in ("main", "article", "#main-content", "#main", "div.main", "body"):
        el = soup.select_one(sel)
        if el is not None and len(el.get_text(strip=True)) > 200:
            return el
    raise ParseError("no main content")


def clean_container(el: Tag) -> Tag:
    for t in el.find_all(DROP_TAGS):
        t.decompose()
    for t in el.find_all(class_=DROP_CLASS):
        t.decompose()
    return el


def page_text(raw: bytes) -> str:
    """The main content's text, normalised: what the lock's text hash covers."""
    soup = BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser")
    return norm(clean_container(main_container(soup)).get_text(" "))


def _blocks(el: Tag, levels: list[str]) -> list[tuple[str, list[str]]]:
    """(heading, lines) in document order. Table rows become 'cell | cell' lines."""
    blocks: list[tuple[str, list[str]]] = [("", [])]
    wanted = ["h1", *levels, "p", "li", "tr", "dd", "dt", "pre", "blockquote"]
    for node in el.find_all(wanted):
        if node.name in ("p", "li") and node.find_parent(["li", "tr", "blockquote"]) is not None:
            continue  # counted with its container
        if node.name == "p" and node.find_parent("li") is not None:
            continue
        if node.name == "tr":
            cells = [norm(c.get_text(" ")) for c in node.find_all(["th", "td"])]
            text = " | ".join(c for c in cells if c)
        else:
            text = norm(node.get_text(" "))
        if not text or LAST_MODIFIED.match(text):
            continue
        if node.name == "h1":
            continue  # the page title is in every chunk header already
        if node.name in levels:
            blocks.append((text, []))
        else:
            blocks[-1][1].append(f"- {text}" if node.name == "li" else text)
    return [(h, lines) for h, lines in blocks if lines]


def parse_html_sections(src: Source, spec: SplitSpec, raw: bytes) -> list[Document]:
    soup = BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser")
    container = clean_container(main_container(soup))
    blocks = _blocks(container, spec.heading_levels)
    drops = [re.compile(x, re.IGNORECASE) for x in spec.drop_headings]
    blocks = [(h, ls) for h, ls in blocks if not (h and any(d.search(h) for d in drops))]
    merged: list[tuple[str, list[str]]] = []
    for heading, lines in blocks:
        if merged and len(" ".join(lines)) < spec.min_chars:
            merged[-1][1].extend([heading, *lines] if heading else lines)
        else:
            merged.append((heading, lines))
    docs, seen = [], set()
    for heading, lines in merged:
        unit = slug(heading) if heading else "overview"
        base, n = unit, 2
        while unit in seen:
            unit, n = f"{base}-{n}", n + 1
        seen.add(unit)
        docs.append(
            Document(
                source_id=src.id,
                unit_id=unit,
                citation=f"{spec.citation_prefix}" + (f" — {heading}" if heading else ""),
                section_id=unit,
                title=heading or "Overview",
                text="\n".join(lines),
            )
        )
    if not docs:
        raise ParseError(f"{src.id}: no text blocks")
    return docs


# --- OFAC FAQ topic page --------------------------------------------------------------------------

FAQ_HEAD = re.compile(r"^(\d{2,4})\.\s+(.*)")


def parse_ofac_faqs(src: Source, spec: SplitSpec, raw: bytes) -> list[Document]:
    soup = BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser")
    container = clean_container(main_container(soup))
    docs: list[Document] = []
    current: tuple[str, str, list[str]] | None = None
    for node in container.find_all(["h1", "h2", "h3", "h4", "p", "li", "tr"]):
        if node.name in ("p",) and node.find_parent(["li", "tr"]) is not None:
            continue
        text = norm(node.get_text(" "))
        if not text:
            continue
        m = FAQ_HEAD.match(text) if node.name.startswith("h") else None
        if m:
            if current:
                docs.append(_faq(src, spec, *current))
            current = (m.group(1), m.group(2), [])
        elif current is not None:
            current[2].append(f"- {text}" if node.name == "li" else text)
    if current:
        docs.append(_faq(src, spec, *current))
    if len(docs) < 10:
        raise ParseError(f"{src.id}: only {len(docs)} FAQs found; page layout changed?")
    return docs


def _faq(src: Source, spec: SplitSpec, num: str, question: str, lines: list[str]) -> Document:
    return Document(
        source_id=src.id,
        unit_id=f"faq-{num}",
        citation=f"{spec.citation_prefix} {num}",
        section_id=f"faq-{num}",
        title=f"FAQ {num}. {question}",
        text="\n".join([f"Q: {question}", *lines]),
    )


# --- USITC HTS JSON rows ---------------------------------------------------------------------------


def parse_hts_json(src: Source, spec: SplitSpec, raw: bytes) -> list[Document]:
    rows = json.loads(raw)
    if not isinstance(rows, list) or not rows:
        raise ParseError(f"{src.id}: no rows")
    docs: list[Document] = []
    parents: dict[int, str] = {}
    for row in rows:
        htsno = (row.get("htsno") or "").strip()
        indent = int(row.get("indent") or 0)
        desc = norm(row.get("description") or "")
        parents[indent] = desc
        for deeper in [k for k in parents if k > indent]:
            del parents[deeper]
        if not htsno or len(htsno) < 10:
            continue  # header rows only provide context
        sub = htsno[:10]
        if spec.hts_prefixes and not any(sub.startswith(p) for p in spec.hts_prefixes):
            continue
        context = " > ".join(parents[k] for k in sorted(parents) if k < indent)
        rates = "; ".join(
            f"{name}: {row.get(key)}"
            for key, name in (("general", "General"), ("special", "Special"), ("other", "Column 2"))
            if row.get(key)
        )
        text = "\n".join(
            x for x in (context, f"{htsno} {desc}", f"Rates of duty: {rates}" if rates else "") if x
        )
        if docs and docs[-1].unit_id == sub:  # statistical suffix rows join their subheading
            docs[-1].text += "\n" + f"{htsno} {desc}"
            continue
        docs.append(
            Document(
                source_id=src.id,
                unit_id=sub,
                citation=f"{spec.citation_prefix} {sub}",
                section_id=sub[:7],
                title=f"Subheading {sub}",
                text=text,
            )
        )
    if not docs:
        raise ParseError(f"{src.id}: no subheadings kept")
    return docs


# --- PDFs -----------------------------------------------------------------------------------------


def pdf_pages(raw: bytes, ranges: list[list[int]]) -> list[tuple[int, list[str]]]:
    reader = PdfReader(io.BytesIO(raw))
    out = []
    for start, end in ranges:
        for i in range(start, end + 1):
            if not 1 <= i <= len(reader.pages):
                raise ParseError(f"page {i} out of range (1..{len(reader.pages)})")
            text = reader.pages[i - 1].extract_text() or ""
            out.append((i, [ln.strip() for ln in text.splitlines() if ln.strip()]))
    return out


def parse_pdf_blocks(src: Source, spec: SplitSpec, raw: bytes) -> list[Document]:
    """Contexts (e.g. "General Note 7") start at context_pattern lines; within a context, units
    start at unit_pattern lines (top-level letters are checked for sequence). Each page range
    can open mid-context: page_contexts gives the label in force at its first line."""
    ranges = spec.pages or [[1, len(PdfReader(io.BytesIO(raw)).pages)]]
    return blocks_from_pages(src, spec, pdf_pages(raw, [list(r) for r in ranges]), ranges)


def blocks_from_pages(
    src: Source,
    spec: SplitSpec,
    page_iter: list[tuple[int, list[str]]],
    ranges: list[list[int]],
) -> list[Document]:
    """The block logic of parse_pdf_blocks, on extracted lines (testable without a PDF)."""
    ctx_re = re.compile(spec.context_pattern) if spec.context_pattern else None
    unit_re = re.compile(spec.unit_pattern) if spec.unit_pattern else None
    drops = [re.compile(p) for p in spec.drop_patterns]
    docs: list[Document] = []
    starts = {
        r[0]: (spec.page_contexts[i] if i < len(spec.page_contexts) else "")
        for i, r in enumerate(ranges)
    }
    context, unit, lines = "", "", []
    seq = LetterSequence()

    def flush() -> None:
        if lines:
            label = f"{context}{unit}".strip()
            uid = slug(label or "text", 64)
            n, base = 2, uid
            while any(d.unit_id == uid for d in docs):
                uid, n = f"{base}-{n}", n + 1
            docs.append(
                Document(
                    source_id=src.id,
                    unit_id=uid,
                    citation=f"{spec.citation_prefix} {label}".strip(),
                    section_id=slug(context or "text", 64),
                    title=label or src.title,
                    text="\n".join(lines),
                )
            )

    for page_no, page_lines in page_iter:
        if starts.get(page_no):
            flush()
            context, unit, lines = starts[page_no], "", []
            seq = LetterSequence()
        for ln in page_lines:
            if any(d.search(ln) for d in drops):
                continue
            cm = ctx_re.search(ln) if ctx_re else None
            if cm:
                flush()
                context = spec.context_template.format(**cm.groupdict())
                unit, lines, seq = "", [ln], LetterSequence()
                continue
            um = unit_re.search(ln) if unit_re else None
            if um:
                uid = um.group("id")
                ok = seq.accept(ln) is not None if spec.letter_sequence else True
                if ok:
                    flush()
                    unit, lines = spec.unit_template.format(id=uid), [ln]
                    continue
            lines.append(ln)
    flush()
    if not docs:
        raise ParseError(f"{src.id}: no blocks")
    return docs


def pdf_text(raw: bytes) -> str:
    reader = PdfReader(io.BytesIO(raw))
    return norm(" ".join((p.extract_text() or "") for p in reader.pages))


# --- synthetic markdown fixtures -------------------------------------------------------------------


def parse_markdown(source_id: str, citation_prefix: str, body: str) -> list[Document]:
    docs: list[Document] = []
    heading, lines = "", []
    for ln in body.splitlines():
        if ln.startswith("## "):
            if lines:
                docs.append(_md(source_id, citation_prefix, heading, lines))
            heading, lines = ln[3:].strip(), []
        elif ln.strip() and not ln.startswith("# "):
            lines.append(ln.strip())
    if lines:
        docs.append(_md(source_id, citation_prefix, heading, lines))
    return docs


def _md(source_id: str, prefix: str, heading: str, lines: list[str]) -> Document:
    unit = slug(heading) if heading else "overview"
    return Document(
        source_id=source_id,
        unit_id=unit,
        citation=f"{prefix}" + (f" — {heading}" if heading else ""),
        section_id=unit,
        title=heading or "Overview",
        text="\n".join(lines),
    )


# --- dispatch ---------------------------------------------------------------------------------------

PARSERS = {
    "ecfr_xml": parse_ecfr_xml,
    "usc_html": parse_usc_html,
    "html_sections": parse_html_sections,
    "ofac_faqs": parse_ofac_faqs,
    "hts_json": parse_hts_json,
    "pdf_blocks": parse_pdf_blocks,
}


def parse(src: Source, spec: SplitSpec, path: Path) -> list[Document]:
    return PARSERS[src.parser](src, spec, path.read_bytes())


def extract_text(src: Source, raw: bytes) -> str:
    """Normalised text of a downloaded file, for the lock's text hash (plan §5.2)."""
    if src.format == "html":
        return page_text(raw)
    if src.format == "xml":
        return norm(" ".join(SafeET.fromstring(raw).itertext()))
    if src.format == "json":
        return json.dumps(json.loads(raw), sort_keys=True, ensure_ascii=False)
    return pdf_text(raw)
