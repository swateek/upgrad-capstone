"""Generic heading splitter: one document per rule/heading.

Each source is configured in the domain pack (corpus/splitting.yaml) with heading patterns.
The splitter knows nothing about any particular instrument.

Rules of the algorithm
- A line starts a section if it matches a heading pattern (at line start).
- `ordered` patterns must be strictly increasing in their numeric key, and may not jump by more
  than `max_jump` at the first level that changes. This rejects table-of-contents lines, list
  items, and numbers like "4.25 lakh" that happen to start a line.
- `reset` patterns (annexures, appendices) always start a section and reset the ordering.
- Footnote blocks (from the first footnote-looking line to the end of a page) are lifted out of
  the body and attached to every section that spans that page, so amendments stay with rules.
- Title-only sections are folded into the next section; long sections are split into parts.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from copilot.ingest.pdf_text import Line, body_font_size


class HeadingPattern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regex: str  # must define (?P<num>...) ; may define (?P<sub>...) and (?P<title>...)
    id_template: str = "{num}{sub}"
    ordered: bool = True
    reset: bool = False  # always accepted; restarts ordering (annexures, appendices)


class SplitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patterns: list[HeadingPattern]
    body_start_page: int = 1
    body_end_page: int | None = None
    # Reset (annexure) headings only count from this page on; earlier mentions are body text.
    annex_start_page: int | None = None
    # Drop everything from annex_start_page on (forms, templates). Ignored if annex_start_page unset.
    exclude_annexures: bool = False
    keep_range: tuple[int, int] | None = None  # first-level numeric range to keep
    max_jump: int = 5
    # Footnotes: lines whose font is at least this many points smaller than the body font.
    # Works wherever the PDF places them in reading order (two-column layouts interleave them).
    footnote_font_delta: float | None = None
    max_tokens: int = 650
    min_body_chars: int = 40


@dataclass
class Section:
    rule_id: str
    title: str
    key: tuple[int, ...] | None
    pages: list[int]
    body: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Piece:
    rule_id: str
    title: str
    part: int
    parts: int
    text: str
    page_start: int
    page_end: int


_INT = re.compile(r"\d+")


def _key(num: str, sub: str) -> tuple[int, ...]:
    return tuple(int(x) for x in _INT.findall(num + " " + sub))


def _acceptable(new: tuple[int, ...], last: tuple[int, ...] | None, max_jump: int) -> bool:
    if last is None:
        return True
    if new <= last:
        return False
    for a, b in zip(new, last, strict=False):
        if a != b:
            return a - b <= max_jump
    return True  # new extends last (e.g. 4.2 -> 4.2.1)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def _strip_footnotes(
    pages: list[list[Line]], delta: float | None
) -> tuple[list[list[Line]], dict[int, list[str]]]:
    if delta is None:
        return pages, {}
    body = body_font_size(pages)
    notes: dict[int, list[str]] = {}
    body_pages: list[list[Line]] = []
    for lines in pages:
        small = [ln for ln in lines if 0 < ln.size <= body - delta]
        body_pages.append([ln for ln in lines if not (0 < ln.size <= body - delta)])
        if small:
            notes[small[0].page] = [ln.text.strip() for ln in small]
    return body_pages, notes


def split_sections(pages: list[list[Line]], spec: SplitSpec) -> list[Section]:
    end = spec.body_end_page or len(pages)
    if spec.exclude_annexures and spec.annex_start_page:
        end = min(end, spec.annex_start_page - 1)
    window = pages[spec.body_start_page - 1 : end]
    window, notes = _strip_footnotes(window, spec.footnote_font_delta)
    compiled = [(re.compile(p.regex), p) for p in spec.patterns]

    sections: list[Section] = []
    last_key: tuple[int, ...] | None = None
    prefix = ""  # set by reset headings: sections after "Annexure-2" become "annexure-2/1.1"
    seen: Counter[str] = Counter()

    def unique(rule_id: str) -> str:
        seen[rule_id] += 1
        return rule_id if seen[rule_id] == 1 else f"{rule_id}~{seen[rule_id]}"

    for line in (ln for page in window for ln in page):
        text = line.text.strip()
        started = False
        for rx, pat in compiled:
            m = rx.match(text)
            if not m:
                continue
            gd = m.groupdict()
            num, sub = gd.get("num") or "", gd.get("sub") or ""
            if pat.reset:
                if spec.annex_start_page and line.page < spec.annex_start_page:
                    continue  # a mention of an annexure in body text, not a heading
                last_key = None
                rule_id = unique(pat.id_template.format(num=num, sub=sub, slug=_slug(num)))
                prefix = rule_id + "/"
                sections.append(Section(rule_id, text, None, [line.page]))
                started = True
                break
            key = _key(num, sub)
            if not key or (pat.ordered and not _acceptable(key, last_key, spec.max_jump)):
                continue
            last_key = key
            rule_id = unique(
                prefix + pat.id_template.format(num=num, sub=sub.replace(" ", ""), slug="")
            )
            title = (gd.get("title") or text[m.end() :]).strip(" :-–")
            sections.append(Section(rule_id, title, key, [line.page]))
            started = True
            break
        if started:
            continue
        if not sections:
            continue  # preamble before the first heading in the body window
        sec = sections[-1]
        if sec.pages[-1] != line.page:
            sec.pages.append(line.page)
        if not sec.title and not sec.body:
            sec.title = text.strip(" :-–")
            continue
        sec.body.append(text)

    for sec in sections:
        for p in sec.pages:
            sec.notes.extend(notes.get(p, []))

    if spec.keep_range is not None:
        lo, hi = spec.keep_range
        sections = [s for s in sections if s.key is None or lo <= s.key[0] <= hi]
    return _fold_title_only(sections, spec.min_body_chars)


def _is_bare_heading(sec: Section, min_chars: int) -> bool:
    """A parent heading with no text of its own (e.g. "7.6 Planning").
    A numbered sentence ("2. This note does not add any rule.") is content, not a heading."""
    del min_chars  # any body text at all means the section has content of its own
    if sec.body or sec.notes:
        return False
    return not sec.title.rstrip().endswith((".", ";"))  # a one-line sentence is content


def _fold_title_only(sections: list[Section], min_chars: int) -> list[Section]:
    out: list[Section] = []
    carry: list[str] = []
    for sec in sections:
        if _is_bare_heading(sec, min_chars):
            carry.append(f"{sec.rule_id} {sec.title}".strip())
            continue
        if carry:
            sec.body = [*[f"[{c}]" for c in carry], *sec.body]
            carry = []
        out.append(sec)
    if carry and out:  # trailing bare headings: keep their text on the last section
        out[-1].body.extend(f"[{c}]" for c in carry)
    return out


NOTES_MARKER = "[Amendment and footnote text on these pages]"


def to_pieces(
    sections: list[Section], count_tokens: Callable[[str], int], max_tokens: int
) -> list[Piece]:
    pieces: list[Piece] = []
    for sec in sections:
        lines = list(sec.body)
        if sec.notes:
            lines += [NOTES_MARKER, *sec.notes]
        blocks = _pack(lines, count_tokens, max_tokens)
        n = len(blocks)
        for i, block in enumerate(blocks, start=1):
            pieces.append(
                Piece(
                    rule_id=sec.rule_id,
                    title=sec.title,
                    part=i,
                    parts=n,
                    text="\n".join(block),
                    page_start=sec.pages[0],
                    page_end=sec.pages[-1],
                )
            )
    return pieces


def _pack(lines: list[str], count_tokens: Callable[[str], int], max_tokens: int) -> list[list[str]]:
    blocks: list[list[str]] = [[]]
    size = 0
    for ln in lines:
        t = count_tokens(ln) + 1
        if blocks[-1] and size + t > max_tokens:
            blocks.append([])
            size = 0
        blocks[-1].append(ln)
        size += t
    return blocks
