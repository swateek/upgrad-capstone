"""
Build the RAG corpus (v2): one document per regulatory unit.

    uv run python data/rag-corpus/fetch_corpus.py              # fetch everything, write corpus/docs/ + MANIFEST.json
    uv run python data/rag-corpus/fetch_corpus.py --only 19cfr148 ofac_cuba_faqs
    uv run python data/rag-corpus/fetch_corpus.py --offline    # rebuild docs from corpus/raw/ only (no network)
    uv run python data/rag-corpus/fetch_corpus.py --check      # verify docs and raw files against MANIFEST.json

Unit (CLAUDE.md, corpus): one CFR section, one U.S. Code subsection, one HTSUS tariff line
or note, one OFAC FAQ, one section of a guidance page. Every document gets front matter:

    doc_id       unique id, e.g. 19cfr148.33, 26usc5754-a, ofac-faq-719, cbp-duty-info--cuba
    citation_id  the id the eval gold and rules.yaml cite, e.g. 19cfr148.33, 26usc5754, cbp-duty-info
    authority    primary_regulation | agency_guidance | tax_rates | state_guidance | hard_negative
    tags, title, heading, source_id, source_url, as_of, fetched_at, raw_file, raw_sha256, text_sha256

Raw downloads are kept gzipped in corpus/raw/ with their SHA-256 (corpus/raw/INDEX.json), so
the snapshot can be rebuilt offline and checked. A file saved by hand as
corpus/raw/<source_id>.<html|pdf|xml> is used before the network (for JavaScript pages).

The script never edits regulatory text: it strips page chrome and converts markup.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
import yaml

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
DOCS = CORPUS / "docs"
RAW = CORPUS / "raw"
RAW_INDEX = RAW / "INDEX.json"
MANIFEST = CORPUS / "MANIFEST.json"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 customs-rag-fetcher"
)
TIMEOUT = 60
PAUSE_S = 1.0
MIN_CHARS = 40

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
OFFLINE = False
REFRESH = False
ECFR_AS_OF: str | None = None  # set from sources.yaml -> ecfr_as_of


def now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def slug(s: str, n: int = 60) -> str:
    return (
        re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower()))
        .strip("-")[:n]
        .strip("-")
    )


def norm_ws(s: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", " ", s)).strip()


# ------------------------------------------------------------------ raw store


def _index() -> dict:
    return json.loads(RAW_INDEX.read_text()) if RAW_INDEX.exists() else {}


def _save_index(idx: dict) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    RAW_INDEX.write_text(json.dumps(dict(sorted(idx.items())), indent=1))


def fetch_raw(source_id: str, key: str, url: str, ext: str) -> tuple[bytes, dict]:
    """Bytes of `url`, cached as corpus/raw/<source_id>__<key>.<ext>.gz.

    Order: hand-saved corpus/raw/<source_id>.<ext> (only when key == "main"), cached gz,
    network. Returns (bytes, raw-info for front matter).
    """
    manual = RAW / f"{source_id}.{ext}"
    name = f"{source_id}__{slug(key, 80)}.{ext}.gz"
    path = RAW / name
    idx = _index()
    if key == "main" and manual.exists():
        data = manual.read_bytes()
        saved = dt.datetime.fromtimestamp(manual.stat().st_mtime, dt.UTC)
        info = {
            "file": manual.name,
            "url": url,
            "sha256": sha256(data),
            "fetched_at": saved.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "saved_by_hand": True,
        }
        idx[manual.name] = info
        _save_index(idx)
        return data, info
    if path.exists() and not REFRESH:
        data = gzip.decompress(path.read_bytes())
        return data, idx.get(name, {"file": name, "url": url, "sha256": sha256(data)})
    if OFFLINE:
        raise RuntimeError(f"offline and no raw copy of {url}")
    data = get(url).content
    RAW.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(data, mtime=0))
    info = {"file": name, "url": url, "sha256": sha256(data), "fetched_at": now()}
    idx[name] = info
    _save_index(idx)
    time.sleep(PAUSE_S)  # be polite to government servers
    return data, info


def get(url: str) -> requests.Response:
    """GET with retry/backoff on 429, 5xx and connection errors; other errors fail at once."""
    for attempt in range(4):
        try:
            r = session.get(url, timeout=TIMEOUT)
        except requests.ConnectionError as e:
            if attempt == 3:
                raise
            print(f"    retry in {2**attempt}s ({e})")
            time.sleep(2**attempt)
            continue
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            print(f"    retry in {2**attempt}s ({r.status_code})")
            time.sleep(2**attempt)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError("unreachable")


# ------------------------------------------------------------------ documents


@dataclass
class Doc:
    doc_id: str
    citation_id: str
    heading: str
    text: str
    source_url: str
    authority: str
    tags: list[str]
    raw: dict
    extra: dict = field(default_factory=dict)


def base_tags(src: dict) -> list[str]:
    return list(src.get("tags", []))


def classify(src: dict, heading: str) -> tuple[str, list[str]]:
    """Authority and tags for one unit, from the source's keyword rules in sources.yaml."""
    authority, tags = src["authority"], base_tags(src)
    h = heading.lower()
    for rule in src.get("heading_rules", []):
        if any(k in h for k in rule["if_any"]):
            tags += rule.get("tags", [])
            authority = rule.get("authority", authority)
    if "off_topic_unless" in src and not any(k in h for k in src["off_topic_unless"]):
        authority = "hard_negative"
        tags.append("off_topic")
    return authority, list(dict.fromkeys(tags))


# -------------------------------------------------------------------- eCFR

_ecfr_dates: dict[int, str] = {}


def ecfr_latest_date(title: int) -> str:
    if title not in _ecfr_dates:
        data, _ = fetch_raw(
            "ecfr",
            "titles",
            "https://www.ecfr.gov/api/versioner/v1/titles.json",
            "json",
        )
        for t in json.loads(data)["titles"]:
            _ecfr_dates[int(t["number"])] = t["up_to_date_as_of"]
    return _ecfr_dates[title]


def section_key(num: str) -> tuple[int, int]:
    part, sec = num.split(".")
    return int(part), int(re.sub(r"\D.*", "", sec) or 0)


def wanted(num: str, spec: dict | None) -> bool:
    if not spec:
        return True
    if "list" in spec:
        return num in spec["list"]
    return section_key(spec["from"]) <= section_key(num) <= section_key(spec["to"])


def fetch_ecfr(src: dict) -> list[Doc]:
    title = int(src["title_number"])
    date = ECFR_AS_OF or ecfr_latest_date(
        title
    )  # pinned in sources.yaml so a rebuild gets the same text
    url = f"https://www.ecfr.gov/api/versioner/v1/full/{date}/title-{title}.xml?part={src['part']}"
    data, raw = fetch_raw(
        src["id"], f"title-{title}-part-{src['part']}-{date}", url, "xml"
    )
    root = ET.fromstring(data)
    parent = {c: p for p in root.iter() for c in p}
    docs = []
    for div in root.iter("DIV8"):
        if div.get("TYPE") != "SECTION":
            continue
        head_el = div.find("HEAD")
        head = norm_ws("".join(head_el.itertext())) if head_el is not None else ""
        m = re.search(r"(\d+\.\d+[a-z]?)", div.get("N", "") or head)
        if not m or not wanted(m.group(1), src.get("sections")):
            continue
        num = m.group(1)
        sub, p = "", parent.get(div)
        while p is not None:
            if p.tag == "DIV6" and p.get("TYPE") == "SUBPART":
                h = p.find("HEAD")
                sub = norm_ws("".join(h.itertext())) if h is not None else ""
                break
            p = parent.get(p)
        paras = []
        for el in div:
            if el.tag == "HEAD":
                continue
            text = norm_ws("".join(el.itertext()))
            if text:
                paras.append(f"_{text}_" if el.tag == "CITA" else text)
        body = "\n\n".join(paras)
        if "[Reserved]" in head or body.strip() in ("", "[Reserved]"):
            continue
        authority, tags = classify(src, f"{sub} {head}")
        if sub:
            tags.append(
                "subpart-" + slug(sub.split("—")[0].replace("Subpart", "").strip(), 10)
            )
        cid = f"{title}cfr{num}"
        docs.append(
            Doc(
                doc_id=cid,
                citation_id=cid,
                heading=f"{sub} > {head}" if sub else head,
                text=body,
                source_url=f"https://www.ecfr.gov/current/title-{title}/section-{num}",
                authority=authority,
                tags=list(dict.fromkeys(tags)),
                raw=raw,
                extra={"as_of": date, "subpart": sub},
            )
        )
    return docs


# ---------------------------------------------------------------- HTML help

CHROME_SELECTORS = [
    "header",
    "footer",
    "nav",
    "script",
    "style",
    "noscript",
    "form",
    "aside",
    ".usa-banner",
    ".breadcrumb",
    ".sidebar",
    ".usa-footer",
    ".usa-header",
    ".skipnav",
    ".menu",
    "#block-cbp-main-menu",
    ".usa-sidenav",
    ".field--name-field-related-content",
    ".usa-identifier",
]
MAIN_SELECTORS = [
    "main",
    "article",
    "#main-content",
    ".main-content",
    "[role=main]",
    "#content",
    "body",
]


def html_to_markdown(html: str | bytes, flatten_tables: bool = False) -> str:
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md

    soup = BeautifulSoup(html, "lxml")
    for sel in CHROME_SELECTORS:
        for el in soup.select(sel):
            el.decompose()
    if flatten_tables:  # layout tables (e-mail bulletins): keep the text, drop the grid
        for tag in soup.find_all(["table", "tbody", "thead", "tr"]):
            tag.name = "div"
        for tag in soup.find_all(["td", "th"]):
            tag.name = "p"
    main = next(
        (soup.select_one(s) for s in MAIN_SELECTORS if soup.select_one(s)), soup
    )
    text = md(str(main), heading_style="ATX", strip=["img"])
    lines = []
    for line in text.splitlines():
        bare = line.strip()
        # drop navigation leftovers: bullet lines that are only a link, and "skip to" links
        if re.fullmatch(
            r"[*+\-]\s*\[[^\]]*\]\([^)]*\)", bare
        ) or bare.lower().startswith("[skip to"):
            continue
        lines.append(line.rstrip())
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return re.sub(
        r"\[([^\]]+)\]\((?!https?://)[^)]*\)", r"\1", out
    )  # keep link text, drop relative targets


def cut(md_text: str, start: str | None, ends: list[str], last: bool = False) -> str:
    """Slice markdown from the first (or last) line matching `start` to the next `ends` match."""
    lines = md_text.splitlines()
    i = 0
    if start:
        hits = [k for k, ln in enumerate(lines) if re.search(start, ln)]
        if not hits:
            return ""
        i = hits[-1] if last else hits[0]
    j = len(lines)
    for k in range(i + 1, len(lines)):
        if any(re.search(e, lines[k]) for e in ends):
            j = k
            break
    return "\n".join(lines[i:j]).strip()


def split_headings(md_text: str, level: int) -> list[tuple[str, str]]:
    """[(heading, body)] split on headings of exactly `level` (#=1); text before the first goes with it."""
    out: list[tuple[str, list[str]]] = []
    cur_head, cur = "", []
    for line in md_text.splitlines():
        m = re.match(rf"^#{{{level}}}\s+(.*)", line)
        if m:
            if cur_head or any(x.strip() for x in cur):
                out.append((cur_head, cur))
            cur_head, cur = m.group(1).strip(), []
        else:
            cur.append(line)
    if cur_head or any(x.strip() for x in cur):
        out.append((cur_head, cur))
    return [(h, "\n".join(b).strip()) for h, b in out]


def page_title(md_text: str) -> str:
    m = re.search(r"(?m)^#\s+(.+)$", md_text)
    return m.group(1).strip() if m else ""


# -------------------------------------------------------------------- HTML


BLOCK_PAGE = re.compile(
    rb"flagged as potentially automated|complete the CAPTCHA|unblock_controller",
    re.IGNORECASE,
)


def fetch_html(src: dict) -> list[Doc]:
    data, raw = fetch_raw(src["id"], "main", src["url"], "html")
    if not raw.get("saved_by_hand") and BLOCK_PAGE.search(data[:50000]):
        (RAW / raw["file"]).unlink(
            missing_ok=True
        )  # never keep a block page as the snapshot
        raise RuntimeError(
            f"{src['url']} returned a bot-check page; save it from a browser as corpus/raw/{src['id']}.html"
        )
    md_text = html_to_markdown(data, flatten_tables=src.get("flatten_tables", False))
    md_text = (
        cut(
            md_text,
            src.get("start"),
            src.get("end", []),
            last=src.get("start_last", False),
        )
        or md_text
    )
    title = page_title(md_text) or src.get(
        "title", ""
    )  # the page's own H1 reads best in headings
    if src.get("split") != "h2":
        md_text = re.sub(
            r"(?m)^#\s+.*\n?", "", md_text
        ).strip()  # the doc heading repeats it
    docs: list[Doc] = []
    parts = (
        split_headings(md_text, 2) if src.get("split") == "h2" else [(title, md_text)]
    )
    for head, body in parts:
        body = re.sub(r"(?m)^#\s+.*$", "", body).strip() if head == "" else body
        head = head or title
        if len(body) < MIN_CHARS:
            continue
        authority, tags = classify(src, head)
        cid = src["citation_id"]
        doc_id = cid if len(parts) == 1 else f"{cid}--{slug(head, 50)}"
        docs.append(
            Doc(
                doc_id=doc_id,
                citation_id=cid,
                heading=f"{title} > {head}" if head != title else title,
                text=body,
                source_url=src["url"],
                authority=authority,
                tags=tags,
                raw=raw,
                extra={"as_of": raw.get("fetched_at", "")[:10]},
            )
        )
    return docs


# --------------------------------------------------------------------- PDF


def pdf_pages(data: bytes) -> list[str]:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return [(p.extract_text() or "") for p in pdf.pages]


def fetch_pdf(src: dict) -> list[Doc]:
    data, raw = fetch_raw(src["id"], "main", src["url"], "pdf")
    pages = pdf_pages(data)
    docs = []
    groups = (
        [(f"page {i}", t) for i, t in enumerate(pages, 1)]
        if src.get("split") == "pages"
        else [("", "\n".join(pages))]
    )
    for label, text in groups:
        text = text.strip()
        if len(text) < MIN_CHARS:
            continue
        authority, tags = classify(src, text[:200])
        cid = src["citation_id"]
        docs.append(
            Doc(
                doc_id=cid if not label else f"{cid}--{slug(label)}",
                citation_id=cid,
                heading=f"{src['title']}" + (f" ({label})" if label else ""),
                text=text,
                source_url=src["url"],
                authority=authority,
                tags=tags,
                raw=raw,
                extra={"as_of": raw.get("fetched_at", "")[:10]},
            )
        )
    return docs


# ---------------------------------------------------------------- U.S. Code

USC_NOTES = re.compile(
    r"^#+\s*(Editorial Notes|Statutory Notes|Amendments|Prior Provisions|Effective Date|"
    r"References in Text|Codification|Short Title|Regulations|Termination|Transfer of Functions|"
    r"Construction|Miscellaneous)",
    re.IGNORECASE,
)


def fetch_usc(src: dict) -> list[Doc]:
    docs = []
    t = src["title_number"]
    for sec in src["sections"]:
        url = f"https://uscode.house.gov/us/usc/t{t}/s{sec}/"  # OLRC: always the current edition
        data, raw = fetch_raw(src["id"], f"{t}usc{sec}", url, "html")
        md_text = html_to_markdown(data)
        lines = md_text.splitlines()
        start = next(
            (k for k, ln in enumerate(lines) if re.match(rf"^#+\s*§\s*{sec}\.", ln)),
            None,
        )
        if start is None:
            raise RuntimeError(f"{t} USC {sec}: section heading not found")
        end = next(
            (k for k in range(start + 1, len(lines)) if USC_NOTES.match(lines[k])),
            len(lines),
        )
        sec_head = re.sub(r"^#+\s*", "", lines[start]).strip()
        body_lines = lines[start + 1 : end]
        cid = f"{t}usc{sec}"
        subs: list[tuple[str, list[str]]] = []
        for ln in body_lines:
            m = re.match(r"^#+\s*\(([a-z])\)\s*(.*)", ln)
            if m:
                subs.append((f"({m.group(1)}) {m.group(2)}".strip(), []))
            elif subs:
                subs[-1][1].append(ln)
            else:
                subs.append(("", [ln]))
        if len([s for s in subs if s[0]]) < 2:
            subs = [("", body_lines)]
        authority, tags = classify(src, sec_head)
        for head, blines in subs:
            body = re.sub(r"\n{3,}", "\n\n", "\n".join(blines)).strip()
            if len(body) < MIN_CHARS and not head:
                continue
            letter = re.match(r"\(([a-z])\)", head)
            doc_id = f"{cid}-{letter.group(1)}" if letter else cid
            docs.append(
                Doc(
                    doc_id=doc_id,
                    citation_id=cid,
                    heading=f"{sec_head} > {head}" if head else sec_head,
                    text=(f"{head}\n\n{body}" if head else body).strip(),
                    source_url=url,
                    authority=authority,
                    tags=tags,
                    raw=raw,
                    extra={"as_of": raw.get("fetched_at", "")[:10]},
                )
            )
    return docs


# ------------------------------------------------------------------- HTSUS


def fetch_hts_lines(src: dict) -> list[Doc]:
    url = f"https://hts.usitc.gov/reststop/exportList?from={src['from']}&to={src['to']}&format=JSON&styles=false"
    data, raw = fetch_raw(src["id"], f"{src['from']}-{src['to']}", url, "json")
    rows = json.loads(data)
    docs, context = [], []
    for r in rows:
        num = (r.get("htsno") or r.get("htsNumber") or "").strip()
        desc = norm_ws(r.get("description", ""))
        indent = int(r.get("indent") or 0)
        if not num:
            context = context[:indent] + [desc]
            continue
        context = context[:indent]
        under = " > ".join(c for c in context if c)
        text = (
            (f"Under: {under}\n\n" if under else "")
            + f"{desc}\n\n"
            + "\n".join(
                [
                    f"- General rate: {r.get('general') or '-'}",
                    f"- Special rate: {r.get('special') or '-'}",
                    f"- Column 2 rate: {r.get('other') or '-'}",
                ]
            )
        )
        authority, tags = classify(src, desc)
        cid = f"htsus{num}"
        docs.append(
            Doc(
                doc_id=cid,
                citation_id=cid,
                heading=f"HTSUS {num}",
                text=text,
                source_url=f"https://hts.usitc.gov/search?query={num}",
                authority=authority,
                tags=tags,
                raw=raw,
                extra={"as_of": raw.get("fetched_at", "")[:10]},
            )
        )
    if not docs:
        raise RuntimeError("HTS API returned no tariff lines")
    return docs


def _pdf_for(src: dict) -> tuple[list[str], dict]:
    """First candidate URL that returns a PDF (a hand-saved corpus/raw/<id>.pdf wins)."""
    if (RAW / f"{src['id']}.pdf").exists():
        data, raw = fetch_raw(src["id"], "main", src["urls"][0], "pdf")
        return pdf_pages(data), raw
    err = None
    for k, url in enumerate(src["urls"]):
        try:
            data, raw = fetch_raw(src["id"], f"candidate-{k}", url, "pdf")
            if not data.startswith(b"%PDF"):
                (RAW / raw["file"]).unlink(
                    missing_ok=True
                )  # do not keep an error page as the snapshot
                raise RuntimeError(f"{url} did not return a PDF")
            return pdf_pages(data), raw
        except Exception as e:  # noqa: BLE001 - try the next candidate URL
            err = e
    raise RuntimeError(f"no PDF ({err}); save it by hand as corpus/raw/{src['id']}.pdf")


HTS_PAGE_NOISE = re.compile(
    r"^(Harmonized Tariff Schedule of the United States.*|Annotated for Statistical Reporting Purposes|"
    r"[IVXL]+|98-[IVXL]+-\d+|GN p\.\d+)\s*$"
)


def _clean_hts(text: str) -> str:
    return "\n".join(
        ln for ln in text.splitlines() if not HTS_PAGE_NOISE.match(ln.strip())
    ).strip()


def fetch_hts_ch98(src: dict) -> list[Doc]:
    """Chapter 98 U.S. Notes for the listed subchapters: one doc per numbered note.

    The notes run from "U.S. Note(s)" to the first tariff table ("Heading/ Stat."); tariff
    lines themselves come from the HTS API (hts_lines).
    """
    pages, raw = _pdf_for(src)
    docs = []
    for sub in src["subchapters"]:  # e.g. IV, XVI
        text = "\n".join(p for p in pages if re.search(rf"98-{sub}-\d", p))
        if not text:
            print(f"    subchapter {sub}: no pages found")
            continue
        m = re.search(
            r"U\.\s?S\.\s+Notes?\s*\n(.*?)(?=^Heading/|\Z)",
            text,
            re.DOTALL | re.MULTILINE,
        )
        if not m:
            print(f"    subchapter {sub}: U.S. Notes not found")
            continue
        notes_text = _clean_hts(m.group(1))
        parts = re.split(r"(?m)^(\d{1,2})\.\s+", notes_text)
        notes = [(parts[k], parts[k + 1]) for k in range(1, len(parts) - 1, 2)]
        for n, body in notes:
            body = body.strip()
            if len(body) < MIN_CHARS:
                continue
            authority, tags = classify(src, body[:300])
            cid = f"htsus-ch98-{sub.lower()}-usnote-{n}"
            docs.append(
                Doc(
                    doc_id=cid,
                    citation_id=cid,
                    heading=f"HTSUS Chapter 98, Subchapter {sub}, U.S. Note {n}",
                    text=body,
                    source_url=raw["url"],
                    authority=authority,
                    tags=tags + [f"subchapter-{sub.lower()}"],
                    raw=raw,
                    extra={"as_of": raw.get("fetched_at", "")[:10]},
                )
            )
    return docs


def _gn_title(text: str) -> str:
    m = re.match(r"\s*\d+\.?\s+(.{3,160}?)\.", text)
    return m.group(1).strip() if m else ""


def fetch_hts_general_notes(src: dict) -> list[Doc]:
    """Selected HTSUS General Notes, found by the running page label (e.g. "General Note 3", "CBERA")."""
    pages, raw = _pdf_for(src)
    docs = []
    for n, label in src["notes"].items():
        n = int(n)
        text = "\n".join(p for p in pages if label in "\n".join(p.splitlines()[:5]))
        start = re.search(rf"(?m)^\s*{n}\.?\s+[A-Z]", text)
        if not text or not start:
            print(f"    general note {n} ({label}): not found")
            continue
        text = text[start.start() :]
        nxt = re.search(rf"(?m)^\s*{n + 1}\.?\s+[A-Z][a-z]", text)
        text = _clean_hts(text[: nxt.start()] if nxt else text)
        authority, tags = classify(src, text[:300])
        cid = f"htsus-gn-{n}"
        docs.append(
            Doc(
                doc_id=cid,
                citation_id=cid,
                heading=f"HTSUS General Note {n}: {_gn_title(text)}",
                text=text,
                source_url=raw["url"],
                authority=authority,
                tags=tags,
                raw=raw,
                extra={"as_of": raw.get("fetched_at", "")[:10]},
            )
        )
    return docs


# ------------------------------------------------------- Federal Register


def fetch_federal_register(src: dict) -> list[Doc]:
    """A Federal Register document through its API (the website blocks scripts)."""
    api = f"https://www.federalregister.gov/api/v1/documents/{src['document_number']}.json"
    meta, _ = fetch_raw(src["id"], "api", api, "json")
    info = json.loads(meta)
    data, raw = fetch_raw(src["id"], "text", info["raw_text_url"], "txt")
    text = data.decode("utf-8", errors="replace")
    text = re.sub(r"<[^>]+>", "", text)  # raw_text is plain text with light markup
    if src.get("start"):
        m = re.search(src["start"], text)
        text = text[m.start() :] if m else text
    for e in src.get("end", []):
        m = re.search(e, text)
        text = text[: m.start()] if m else text
    authority, tags = classify(src, info.get("title", ""))
    return [
        Doc(
            doc_id=src["citation_id"],
            citation_id=src["citation_id"],
            heading=info.get("title", src["title"]),
            text=text.strip(),
            source_url=info.get("html_url", api),
            authority=authority,
            tags=tags,
            raw=raw,
            extra={"as_of": info.get("publication_date", "")},
        )
    ]


# -------------------------------------------------------------------- OFAC


def fetch_ofac_faqs(src: dict) -> list[Doc]:
    ids: list[int] = list(src.get("ids", []))
    if src.get("listing"):
        seen_pages = 0
        for page in range(src.get("max_pages", 30)):
            url = src["listing"].format(page=page)
            data, _ = fetch_raw(src["id"], f"listing-{page}", url, "html")
            found = [
                int(x)
                for x in re.findall(
                    rb'href="(?:https://ofac\.treasury\.gov)?/faqs/(\d+)"', data
                )
            ]
            new = [i for i in found if i not in ids]
            if not new:
                break
            ids += new
            seen_pages += 1
        print(f"    {len(set(ids))} FAQs from {seen_pages} listing pages")
    docs = []
    for i in dict.fromkeys(ids):
        url = f"https://ofac.treasury.gov/faqs/{i}"
        data, raw = fetch_raw(src["id"], f"faq-{i}", url, "html")
        md_text = html_to_markdown(data)
        body = cut(md_text, rf"^#+\s*{i}\.", [r"^#+\s*Similar FAQs", r"^#+\s*Related"])
        if not body:
            print(f"    FAQ {i}: question heading not found; skipped")
            continue
        q = re.sub(r"^#+\s*", "", body.splitlines()[0]).strip()
        answer = "\n".join(body.splitlines()[1:]).strip()
        topic = re.search(r"\*\*\[?([A-Z][^\]*]+Sanctions)\]?", md_text)
        authority, tags = classify(src, q)
        cid = f"ofac-faq-{i}"
        docs.append(
            Doc(
                doc_id=cid,
                citation_id=cid,
                heading=f"OFAC FAQ {q}",
                text=answer,
                source_url=url,
                authority=authority,
                tags=tags,
                raw=raw,
                extra={
                    "as_of": raw.get("fetched_at", "")[:10],
                    "topic": topic.group(1) if topic else "",
                },
            )
        )
    return docs


# -------------------------------------------------------------------- main

FETCHERS = {
    "ecfr": fetch_ecfr,
    "html": fetch_html,
    "pdf": fetch_pdf,
    "usc": fetch_usc,
    "hts_lines": fetch_hts_lines,
    "hts_ch98": fetch_hts_ch98,
    "hts_general_notes": fetch_hts_general_notes,
    "ofac_faqs": fetch_ofac_faqs,
    "federal_register": fetch_federal_register,
}


def write_doc(src: dict, d: Doc) -> Path:
    text = d.text.strip()
    meta = {
        "doc_id": d.doc_id,
        "citation_id": d.citation_id,
        "title": src["title"],
        "heading": d.heading,
        "source_id": src["id"],
        "source_url": d.source_url,
        "authority": d.authority,
        "tags": d.tags,
        **{k: v for k, v in d.extra.items() if v},
        "fetched_at": d.raw.get("fetched_at", ""),
        "raw_file": d.raw.get("file", ""),
        "raw_sha256": d.raw.get("sha256", ""),
        "text_sha256": sha256(text.encode()),
    }
    path = DOCS / f"{d.doc_id}.md"
    path.write_text(
        "---\n"
        + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
        + "---\n\n"
        + f"# {d.heading}\n\n{text}\n",
        encoding="utf-8",
    )
    return path


def read_front(path: Path) -> dict:
    t = path.read_text(encoding="utf-8")
    end = t.find("\n---", 4)
    return yaml.safe_load(t[4:end]) or {}


def build_manifest(dropped: list[dict]) -> dict:
    idx = {
        k: v for k, v in _index().items() if (RAW / v["file"]).exists()
    }  # forget deleted downloads
    _save_index(idx)
    docs = []
    for p in sorted(DOCS.glob("*.md")):
        m = read_front(p)
        docs.append(
            {
                k: m.get(k)
                for k in (
                    "doc_id",
                    "citation_id",
                    "source_id",
                    "authority",
                    "text_sha256",
                )
            }
            | {"file": p.name, "file_sha256": sha256(p.read_bytes())}
        )
    by = lambda k: dict(
        sorted({d[k]: sum(1 for x in docs if x[k] == d[k]) for d in docs}.items())
    )
    return {
        "built_at": now(),
        "doc_count": len(docs),
        "by_source": by("source_id"),
        "by_authority": by("authority"),
        "docs": docs,
        "raw": list(idx.values()),
        "dropped": dropped,
    }


def check() -> int:
    man = json.loads(MANIFEST.read_text())
    bad = 0
    for d in man["docs"]:
        p = DOCS / d["file"]
        if not p.exists() or sha256(p.read_bytes()) != d["file_sha256"]:
            print(f"changed or missing: {d['file']}")
            bad += 1
    for r in man["raw"]:
        p = RAW / r["file"]
        if (
            not p.exists()
        ):  # e.g. a large PDF kept out of git; its hash is still recorded
            print(f"raw not present (not committed?): {r['file']}")
            continue
        data = p.read_bytes()
        data = gzip.decompress(data) if p.suffix == ".gz" else data
        if sha256(data) != r["sha256"]:
            print(f"raw changed: {r['file']}")
            bad += 1
    extra = {p.name for p in DOCS.glob("*.md")} - {d["file"] for d in man["docs"]}
    for name in sorted(extra):
        print(f"not in manifest: {name}")
    print(
        f"{man['doc_count']} docs, {len(man['raw'])} raw files: {'OK' if not bad and not extra else 'MISMATCH'}"
    )
    return 1 if bad or extra else 0


def main() -> int:
    global OFFLINE, REFRESH
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="source ids to (re)build")
    ap.add_argument("--offline", action="store_true", help="use corpus/raw only")
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="ignore cached raw files and download again",
    )
    ap.add_argument(
        "--check", action="store_true", help="verify against MANIFEST.json and exit"
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.check:
        return check()
    OFFLINE, REFRESH = args.offline, args.refresh

    global ECFR_AS_OF
    manifest = yaml.safe_load((ROOT / "sources.yaml").read_text())
    ECFR_AS_OF = manifest.get("ecfr_as_of")
    sources = manifest["sources"]
    if args.only:
        sources = [s for s in sources if s["id"] in set(args.only)]
    DOCS.mkdir(parents=True, exist_ok=True)
    ok, failed, dropped = [], [], []
    seen_text: dict[str, str] = {}
    for p in DOCS.glob(
        "*.md"
    ):  # texts already on disk from other sources (for --only runs)
        m = read_front(p)
        if m.get("source_id") not in {s["id"] for s in sources}:
            seen_text[m.get("text_sha256", "")] = m.get("doc_id", "")
    for src in sources:
        print(f"- {src['id']} ({src['kind']})")
        if args.dry_run:
            continue
        try:
            docs = FETCHERS[src["kind"]](src)
        except Exception as e:  # noqa: BLE001 - keep going; report failures at the end
            failed.append({"id": src["id"], "error": str(e)})
            print(f"    FAILED: {e}")
            continue
        for old in DOCS.glob("*.md"):  # replace this source's previous docs
            if read_front(old).get("source_id") == src["id"]:
                old.unlink()
        written = 0
        for d in docs:
            h = sha256(d.text.strip().encode())
            if len(d.text.strip()) < MIN_CHARS:
                dropped.append({"doc_id": d.doc_id, "reason": "too short"})
                continue
            if h in seen_text:
                dropped.append(
                    {"doc_id": d.doc_id, "reason": f"duplicate of {seen_text[h]}"}
                )
                continue
            seen_text[h] = d.doc_id
            write_doc(src, d)
            written += 1
        ok.append({"id": src["id"], "docs": written})
        print(f"    {written} docs")
    if args.dry_run:
        return 0
    man = build_manifest(dropped)
    MANIFEST.write_text(json.dumps(man, indent=1, ensure_ascii=False))
    (CORPUS / "fetch_report.json").write_text(
        json.dumps(
            {"run_at": now(), "ok": ok, "failed": failed, "dropped": dropped}, indent=1
        )
    )
    print(
        f"\n{man['doc_count']} docs in corpus/docs ({', '.join(f'{k} {v}' for k, v in man['by_authority'].items())})"
    )
    print(
        f"{len(failed)} sources failed, {len(dropped)} docs dropped. See corpus/fetch_report.json"
    )
    target = (500, 840)
    if not target[0] <= man["doc_count"] <= target[1]:
        print(f"note: target is {target[0]}-{target[1]} documents")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
