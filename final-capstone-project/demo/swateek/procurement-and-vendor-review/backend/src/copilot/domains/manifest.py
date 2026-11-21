"""Source manifest (hand-edited) and manifest lock (generated hashes)."""

from __future__ import annotations

import fnmatch
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

LOCK_NAME = "manifest.lock.yaml"


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    store: Literal["policy", "screening", "model_tender"]
    instrument: str | None
    title: str
    url: str
    source_page: str
    alt_urls: list[str] = []
    edition: str
    edition_date: date | None
    index_scope: str | None = None
    language: str = "en"


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str
    checked_on: date
    sources: list[Source]


class LockEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    sha256: str
    bytes: int
    retrieved_at: str
    alt_urls_same_file: dict[str, bool] = {}


class ManifestLock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str
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


def load_manifest(path: Path) -> Manifest:
    manifest = Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    ids = [s.id for s in manifest.sources]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate source ids in manifest: {sorted(dupes)}")
    return manifest


def load_lock(path: Path) -> ManifestLock | None:
    if not path.exists():
        return None
    return ManifestLock.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_exclusions(path: Path) -> Exclusions:
    return Exclusions.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
