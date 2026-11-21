"""PDF -> per-page lines (with dominant font size), repeated page headers/footers removed."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf

_DIGITS = re.compile(r"\d+")


@dataclass(frozen=True)
class Line:
    page: int  # 1-based
    text: str
    size: float = 0.0  # dominant font size of the line (by character count)


def _norm(line: str) -> str:
    return _DIGITS.sub("#", line.strip().lower())


_ENUMERATOR = re.compile(r"^\(?(?:\d{1,3}(?:\.\d{1,3})*|[a-zA-Z]|[ivxIVX]{1,5})[.)]?\)?$")


def _page_lines(page: pymupdf.Page, page_no: int) -> list[Line]:
    """Rebuild visual lines per block: spans on the same baseline (±2pt) are one line.
    Justified text is otherwise returned word-by-word by PyMuPDF's dict mode.
    A bare list number ("6.", "2.1.", "(iii)") that sits in its own block is joined to the
    text on the same baseline, so "6." + "Margin of Purchase Preference: ..." is one line."""
    placed: list[tuple[float, float, Line]] = []
    for block in page.get_text("dict")["blocks"]:
        rows: list[tuple[float, list[tuple[float, str, float]]]] = []
        for line in block.get("lines", []):
            y = line["bbox"][1]
            for span in line["spans"]:
                if not span["text"].strip():
                    continue
                item = (span["bbox"][0], span["text"], span["size"])
                for ry, items in rows:
                    if abs(ry - y) <= 2.0:
                        items.append(item)
                        break
                else:
                    rows.append((y, [item]))
        for y, items in sorted(rows, key=lambda r: r[0]):
            items.sort(key=lambda it: it[0])
            text = " ".join(t.strip() for _, t, _ in items)
            weights: Counter[float] = Counter()
            for _, t, s in items:
                weights[round(s, 1)] += len(t.strip())
            placed.append((y, items[0][0], Line(page_no, text, weights.most_common(1)[0][0])))

    used: set[int] = set()
    out: list[Line] = []
    for i, (y, x, ln) in enumerate(placed):
        if i in used:
            continue
        if _ENUMERATOR.match(ln.text.strip()):
            partner = min(
                (
                    j
                    for j, (y2, x2, _) in enumerate(placed)
                    if j != i and j not in used and abs(y2 - y) <= 2.0 and x2 > x
                ),
                key=lambda j: placed[j][1],
                default=None,
            )
            if partner is not None:
                used.add(partner)
                other = placed[partner][2]
                ln = Line(page_no, f"{ln.text.strip()} {other.text}", other.size)
        out.append(ln)
    return out


def read_pdf_lines(path: Path, *, header_footer_share: float = 0.4) -> list[list[Line]]:
    """Return lines per page. Lines that recur (digits ignored) on at least
    `header_footer_share` of pages and are short are treated as running headers/footers."""
    with pymupdf.open(path) as doc:
        raw = [_page_lines(page, i) for i, page in enumerate(doc, start=1)]
    counts: Counter[str] = Counter()
    for lines in raw:
        counts.update({_norm(x.text) for x in lines})
    threshold = max(3, int(len(raw) * header_footer_share))
    boiler = {k for k, n in counts.items() if n >= threshold and len(k) < 120}
    return [[ln for ln in lines if _norm(ln.text) not in boiler] for lines in raw]


def body_font_size(pages: list[list[Line]]) -> float:
    weights: Counter[float] = Counter()
    for lines in pages:
        for ln in lines:
            weights[ln.size] += len(ln.text)
    return weights.most_common(1)[0][0] if weights else 0.0
