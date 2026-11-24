"""Source manifest (hand-edited), manifest lock (generated hashes), exclusions, and the
per-source splitting rules. Same pattern as the reference app, extended for HTML/XML/JSON
sources (plan §5)."""

from __future__ import annotations

import fnmatch
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

LOCK_NAME = "manifest.lock.yaml"

Format = Literal["xml", "html", "pdf", "json"]
Parser = Literal["ecfr_xml", "usc_html", "html_sections", "ofac_faqs", "hts_json", "pdf_blocks"]
Topic = Literal[
    "exemptions",  # personal exemption amounts, alcohol and tobacco allowances
    "rates",  # duty and excise rates
    "sanctions",  # Cuba
    "state",  # arrival-state alcohol rules
    "declaring",  # general traveller procedure
    "other_goods",  # hard negatives: food, money, shipped goods, crew
]


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    publisher: str
    url: str
    source_page: str
    format: Format
    parser: Parser
    topic: Topic
    role: Literal["core", "hard_negative", "flag"] = "core"
    edition: str
    edition_date: date | None
    index_scope: str | None = None  # human-readable; the machine rule is in splitting.yaml
    language: str = "en"

    @property
    def suffix(self) -> str:
        return {"xml": ".xml", "html": ".html", "pdf": ".pdf", "json": ".json"}[self.format]


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checked_on: date
    sources: list[Source]


class LockEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    sha256: str  # raw bytes as downloaded
    text_sha256: str  # normalised extracted text; what verification compares (plan §5.2)
    bytes: int
    retrieved_at: str


class ManifestLock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: dict[str, LockEntry]


class Exclusions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url_patterns: list[str]
    reasons: dict[str, str] = {}

    def match(self, url: str) -> str | None:
        for pattern in self.url_patterns:
            if fnmatch.fnmatch(url, pattern):
                return pattern
        return None


class SplitSpec(BaseModel):
    """How one source becomes documents (one document = one citable unit)."""

    model_config = ConfigDict(extra="forbid")

    citation_prefix: str  # "19 CFR", "26 USC", "OFAC FAQ", "HTSUS", or a page title
    # pdf_blocks
    pages: list[list[int]] = Field(default_factory=list)  # inclusive 1-based page ranges
    page_contexts: list[str] = Field(default_factory=list)  # label in force at each range start
    context_pattern: str | None = None  # a matching line starts a new context (named groups)
    context_template: str = "{id}"
    unit_pattern: str | None = None  # a matching line starts a unit; needs a group named "id"
    unit_template: str = "({id})"
    letter_sequence: bool = False  # units are (a), (b), ...: accept only the next letter
    drop_patterns: list[str] = Field(default_factory=list)  # running headers and footers
    # html_sections
    content_selector: str | None = None  # CSS selector of the content when the page has no <main>
    drop_headings: list[str] = Field(default_factory=list)  # page furniture (footers, contacts)
    heading_levels: list[str] = Field(default_factory=lambda: ["h2", "h3"])  # html_sections
    hts_prefixes: list[str] = Field(default_factory=list)  # hts_json: headings to keep
    max_tokens: int = 450  # longer documents are split into parts that share the citation
    min_chars: int = 40  # shorter blocks merge into the previous one


def load_manifest(path: Path) -> Manifest:
    manifest = Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    ids = [s.id for s in manifest.sources]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate source ids in manifest: {sorted(dupes)}")
    urls = [s.url for s in manifest.sources]
    dupe_urls = {u for u in urls if urls.count(u) > 1}
    if dupe_urls:
        raise ValueError(f"duplicate source urls in manifest: {sorted(dupe_urls)}")
    return manifest


def load_lock(path: Path) -> ManifestLock | None:
    if not path.exists():
        return None
    return ManifestLock.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_exclusions(path: Path) -> Exclusions:
    return Exclusions.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_splitting(path: Path) -> dict[str, SplitSpec]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {})
    return {k: SplitSpec(**{**defaults, **v}) for k, v in raw["sources"].items()}
