"""
Download the official source texts listed in sources.yaml and write one
markdown file per source to corpus/primary/, each with YAML front matter
that the chunker copies onto every chunk.

    uv add requests pyyaml beautifulsoup4 lxml markdownify   # once, from customs-agent/
    uv run python data/rag-corpus/fetch_corpus.py                 # fetch everything
    python fetch_corpus.py --only ofac_faq_719 cbp_types_of_exemptions
    python fetch_corpus.py --dry-run       # show what would be fetched

Network notes
- eCFR and HTS have public JSON/XML APIs and work from scripts.
- cbp.gov sometimes blocks non-browser clients. If a CBP page fails, open it
  in a browser, "Save page as" HTML into corpus/raw/<id>.html, and re-run:
  the script uses a saved file in corpus/raw/ before trying the network.
- The HTSUS Chapter 98 notes (alcohol/tobacco quantity limits) live in the
  chapter PDF. Save it as corpus/raw/htsus_chapter98.pdf; the script extracts
  Subchapter IV notes into corpus/primary/htsus_ch98_notes.md.

This script never edits the regulatory text: it only strips page chrome
and converts markup to markdown.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
import yaml

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "corpus" / "primary"
RAW = ROOT / "corpus" / "raw"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 customs-rag-fetcher"
)
TIMEOUT = 60

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})


# ----------------------------------------------------------------- helpers
def get(url: str, **kw) -> requests.Response:
    """GET with retry/backoff on 429, 5xx and connection errors; other errors fail at once."""
    for attempt in range(4):
        try:
            r = session.get(url, timeout=TIMEOUT, **kw)
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


def front_matter(src: dict, extra: dict) -> str:
    meta = {
        "id": src["id"],
        "title": src["title"],
        "source_url": src["url"],
        "authority": src["authority"],
        "tags": src.get("tags", []),
        "fetched_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **extra,
    }
    return (
        "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True) + "---\n\n"
    )


def write(src: dict, body: str, extra: dict | None = None) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{src['id']}.md"
    path.write_text(
        front_matter(src, extra or {}) + body.strip() + "\n", encoding="utf-8"
    )
    return path


def norm_ws(s: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", " ", s)).strip()


# -------------------------------------------------------------------- eCFR
_ecfr_dates: dict[int, str] = {}


def ecfr_latest_date(title: int) -> str:
    if title not in _ecfr_dates:
        data = get("https://www.ecfr.gov/api/versioner/v1/titles.json").json()
        for t in data["titles"]:
            _ecfr_dates[int(t["number"])] = t["up_to_date_as_of"]
    return _ecfr_dates[title]


def section_key(num: str) -> tuple[int, int]:
    part, sec = num.split(".")
    return int(part), int(sec)


def wanted(num: str, spec: dict) -> bool:
    if "list" in spec:
        return num in spec["list"]
    lo, hi = section_key(spec["from"]), section_key(spec["to"])
    return lo <= section_key(num) <= hi


def ecfr_xml_to_sections(xml_text: str) -> list[tuple[str, str, str]]:
    """Return [(section_number, heading, markdown_body)] from eCFR XML."""
    root = ET.fromstring(xml_text)
    out = []
    for div in root.iter("DIV8"):
        if div.get("TYPE") != "SECTION":
            continue
        head_el = div.find("HEAD")
        head = norm_ws("".join(head_el.itertext())) if head_el is not None else ""
        m = re.search(r"(\d+\.\d+)", div.get("N", "") or head)
        if not m:
            continue
        num = m.group(1)
        paras = []
        for el in div:
            if el.tag == "HEAD":
                continue
            text = norm_ws("".join(el.itertext()))
            if not text:
                continue
            if el.tag == "CITA":
                paras.append(f"_{text}_")
            else:
                paras.append(text)
        out.append((num, head, "\n\n".join(paras)))
    return out


_ecfr_parts: dict[str, str] = {}


def fetch_ecfr(src: dict) -> Path:
    title = int(src["title_number"])
    date = ecfr_latest_date(title)
    url = (
        f"https://www.ecfr.gov/api/versioner/v1/full/{date}/"
        f"title-{title}.xml?part={src['part']}"
    )
    if url not in _ecfr_parts:  # several sources share one part: download once
        _ecfr_parts[url] = get(url).text
    xml_text = _ecfr_parts[url]
    sections = [
        s for s in ecfr_xml_to_sections(xml_text) if wanted(s[0], src["sections"])
    ]
    if not sections:
        raise RuntimeError("no matching sections found in eCFR response")
    body = "\n\n".join(f"## {head}\n\n{text}" for _, head, text in sections)
    return write(
        src,
        f"# {src['title']}\n\n{body}",
        {
            "effective_as_of": date,
            "sections": [n for n, _, _ in sections],
            "api_url": url,
        },
    )


# --------------------------------------------------------------------- HTS
def fetch_hts(src: dict) -> Path:
    url = (
        "https://hts.usitc.gov/reststop/exportList"
        f"?from={src['from']}&to={src['to']}&format=JSON&styles=false"
    )
    rows = get(url).json()
    lines = []
    for r in rows:
        num = r.get("htsno") or r.get("htsNumber") or ""
        desc = norm_ws(r.get("description", ""))
        general = r.get("general", "")
        special = r.get("special", "")
        other = r.get("other", "")
        lines.append(
            f"## {num}\n\n{desc}\n\n"
            f"- General rate: {general or '-'}\n"
            f"- Special rate: {special or '-'}\n"
            f"- Column 2 rate: {other or '-'}"
        )
    if not lines:
        raise RuntimeError("HTS API returned no rows")
    body = f"# {src['title']}\n\n" + "\n\n".join(lines)
    if src.get("note"):
        body += f"\n\n> Note: {src['note']}"
    return write(src, body, {"api_url": url})


def extract_ch98_notes() -> Path | None:
    """Pull Subchapter IV U.S. notes out of a saved Chapter 98 PDF, if present."""
    pdf = RAW / "htsus_chapter98.pdf"
    if not pdf.exists():
        return None
    try:
        import pdfplumber
    except ImportError:
        print("    pdfplumber not installed; skipping Chapter 98 notes")
        return None
    with pdfplumber.open(pdf) as doc:
        text = "\n".join((p.extract_text() or "") for p in doc.pages)
    m = re.search(
        r"SUBCHAPTER IV(.*?)(?=SUBCHAPTER V\b)", text, re.DOTALL | re.IGNORECASE
    )
    if not m:
        print("    could not locate Subchapter IV in the PDF; check the file")
        return None
    src = {
        "id": "htsus_ch98_subchapter4_notes",
        "title": "HTSUS Chapter 98, Subchapter IV - U.S. Notes (personal exemptions, alcohol and tobacco limits)",
        "url": "https://hts.usitc.gov/",
        "authority": "primary_regulation",
        "tags": [
            "exemption_800",
            "alcohol_allowance",
            "tobacco_allowance",
            "30_day_rule",
        ],
    }
    return write(
        src, f"# {src['title']}\n\n" + m.group(0).strip(), {"extracted_from": pdf.name}
    )


# -------------------------------------------------------------------- HTML
CHROME_SELECTORS = [
    "header",
    "footer",
    "nav",
    "script",
    "style",
    "noscript",
    "form",
    ".usa-banner",
    ".breadcrumb",
    "#block-cbp-main-menu",
    ".sidebar",
    ".usa-footer",
    ".usa-header",
    ".skipnav",
]
MAIN_SELECTORS = [
    "main",
    "article",
    "#main-content",
    ".main-content",
    "[role=main]",
    "body",
]


def html_to_markdown(html: str) -> str:
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md

    soup = BeautifulSoup(html, "lxml")
    for sel in CHROME_SELECTORS:
        for el in soup.select(sel):
            el.decompose()
    main = next(
        (soup.select_one(s) for s in MAIN_SELECTORS if soup.select_one(s)), soup
    )
    text = md(str(main), heading_style="ATX", strip=["img"])
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_html(src: dict) -> Path:
    saved = RAW / f"{src['id']}.html"
    if saved.exists():
        html, origin = (
            saved.read_text(encoding="utf-8", errors="ignore"),
            f"saved:{saved.name}",
        )
    else:
        html, origin = get(src["url"]).text, "network"
    body = html_to_markdown(html)
    if len(body) < 300:
        raise RuntimeError(
            f"page body suspiciously short ({len(body)} chars); "
            f"save it manually to corpus/raw/{src['id']}.html"
        )
    return write(src, f"# {src['title']}\n\n{body}", {"retrieved_via": origin})


# -------------------------------------------------------------------- main
FETCHERS = {"ecfr": fetch_ecfr, "hts": fetch_hts, "html": fetch_html}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="source ids to fetch")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sources = yaml.safe_load((ROOT / "sources.yaml").read_text())["sources"]
    if args.only:
        sources = [s for s in sources if s["id"] in set(args.only)]

    ok, failed = [], []
    for src in sources:
        print(f"- {src['id']} ({src['kind']})")
        if args.dry_run:
            print(f"    would fetch {src['url']}")
            continue
        try:
            path = FETCHERS[src["kind"]](src)
            ok.append(src["id"])
            print(f"    wrote {path.relative_to(ROOT)}")
        except Exception as e:  # noqa: BLE001 - keep going; report failures at the end
            failed.append((src["id"], str(e)))
            print(f"    FAILED: {e}")
        time.sleep(1)  # be polite to government servers

    if args.dry_run:
        return 0

    if not args.only:
        notes = extract_ch98_notes()
        if notes:
            print(f"- wrote {notes.relative_to(ROOT)}")
        else:
            print(
                "- Chapter 98 notes: save the PDF to corpus/raw/htsus_chapter98.pdf to include them"
            )

    report = {
        "fetched": ok,
        "failed": [{"id": i, "error": e} for i, e in failed],
        "run_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    (ROOT / "corpus" / "fetch_report.json").write_text(json.dumps(report, indent=2))
    print(f"\n{len(ok)} fetched, {len(failed)} failed. See corpus/fetch_report.json")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
