"""Build the screening snapshot from the GeM delist PDF (procurement domain only).

    cd backend && uv run python ../domains/procurement/pipelines/build_screening.py

Reads data/raw/procurement/gem_delisted_sellers.pdf (hash-checked against manifest.lock.yaml),
extracts every table row with its "As on" section date, and writes
domains/procurement/data/screening/gem_delisted_sellers.csv plus snapshot.yaml.
Screening rows never go into the vector index.
"""

from __future__ import annotations

import csv
import hashlib
import re
import sys
from pathlib import Path

import pymupdf
import yaml

DOMAIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOMAIN_DIR))
from copilot.config import get_settings
from copilot.domains.manifest import LOCK_NAME, load_lock, load_manifest
from screening import normalize

SOURCE_ID = "gem_delisted_sellers"
AS_ON = re.compile(r"As on\s+(\d{1,2})-([A-Za-z]{3})-(\d{4})")
MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ],
        1,
    )
}
DISCLAIMER = (
    "The inclusion of any seller, brand, or catalog in this list is only for the purposes of "
    "determining eligibility for participation in procurement through GeM and shall not be "
    "construed as a finding regarding the quality, credibility, reputation, financial standing, "
    "or overall business suitability of such seller or brand. (GeM disclaimer, page 1)"
)


def iso(match: re.Match[str]) -> str:
    d, mon, y = match.groups()
    return f"{y}-{MONTHS[mon.title()]:02d}-{int(d):02d}"


def cell_text(page: pymupdf.Page, bbox) -> str:
    if bbox is None:
        return ""
    return " ".join(page.get_text("text", clip=pymupdf.Rect(bbox)).split())


def main() -> int:
    settings = get_settings()
    manifest = load_manifest(DOMAIN_DIR / "corpus" / "manifest.yaml")
    src = next(s for s in manifest.sources if s.id == SOURCE_ID)
    lock = load_lock(DOMAIN_DIR / "corpus" / LOCK_NAME)
    pdf = settings.data_dir / "raw" / "procurement" / f"{SOURCE_ID}.pdf"
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != lock.files[SOURCE_ID].sha256:
        print(f"FAIL {pdf.name} does not match {LOCK_NAME}", file=sys.stderr)
        return 1

    rows: list[dict[str, str]] = []
    list_date = None
    with pymupdf.open(pdf) as doc:
        for page_no, page in enumerate(doc, start=1):
            # "As on <date>" markers can sit mid-page: rows above a marker belong to the
            # previous section. Collect (y, date) for every marker on the page.
            markers = []
            for block in page.get_text("blocks"):
                for m in AS_ON.finditer(block[4]):
                    markers.append((block[1], iso(m)))
            markers.sort()
            for table in page.find_tables().tables:
                for row in table.rows:
                    row_y = row.bbox[1]
                    for y, date in markers:
                        if y <= row_y:
                            list_date = date
                    cells = [cell_text(page, c) for c in row.cells]
                    cells = [c for c in cells if c != ""] if len(cells) > 4 else cells
                    if len(cells) < 4 or not cells[0].strip().isdigit():
                        continue  # header rows ("Sr. No.", "Supplier Name", ...)
                    sr, supplier, category, brand = (
                        cells[0],
                        cells[1],
                        cells[2],
                        cells[3],
                    )
                    rows.append(
                        {
                            "row_id": f"{list_date}#{int(sr):03d}",
                            "supplier_name": supplier,
                            "brand": brand,
                            "category": category,
                            "normalized_supplier": normalize(supplier),
                            "normalized_brand": normalize(brand),
                            "source_list": SOURCE_ID,
                            "list_section_date": list_date,
                            "page": str(page_no),
                        }
                    )

    # The five "As on" sections are successive versions of one list (each newer version is a
    # subset of the older ones). Decided 12 Nov 2026: present/not_present uses the latest
    # version only; older versions are history the tool may mention, never a "present" finding.
    snapshot_date = max(r["list_section_date"] for r in rows)
    seen: dict[str, int] = {}
    for r in rows:
        r["in_latest_version"] = "true" if r["list_section_date"] == snapshot_date else "false"
        seen[r["row_id"]] = seen.get(r["row_id"], 0) + 1
        if seen[r["row_id"]] > 1:  # the source repeats a serial number once
            r["row_id"] = f"{r['row_id']}~{seen[r['row_id']]}"
    out_dir = DOMAIN_DIR / "data" / "screening"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / f"{SOURCE_ID}.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    sections: dict[str, int] = {}
    for r in rows:
        sections[r["list_section_date"]] = sections.get(r["list_section_date"], 0) + 1
    meta = {
        "lists": [
            {
                "id": SOURCE_ID,
                "title": src.title,
                "file": f"{SOURCE_ID}.csv",
                "source_url": src.url,
                "sha256": lock.files[SOURCE_ID].sha256,
                # Decided 12 Nov 2026: answers cite the list's own latest "As on" date.
                "snapshot_date": snapshot_date,
                "versions": dict(sorted(sections.items(), reverse=True)),
                "version_semantics": (
                    "Each 'As on' section is a full version of the list. Only the latest version "
                    "decides present/not_present; a name found only in older versions is reported "
                    "as history, with no claim about why it was removed."
                ),
                "rows": len(rows),
                "scope": "Eligibility to participate on GeM only (GFR Rule 144(xi), GTC clause 26).",
                "disclaimer": DISCLAIMER,
                "synthetic": False,
            }
        ]
    }
    (out_dir / "snapshot.yaml").write_text(
        "# Generated by pipelines/build_screening.py (plus hand-kept synthetic entries below it).\n"
        + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    print(f"{len(rows)} rows; versions {sections}; snapshot {snapshot_date}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
