"""Download every source in pack/corpus/manifest.yaml into data/raw/customs/ and verify or
freeze the hashes.

    uv run python -m customs.ingest.download            # download, verify against the lock
    uv run python -m customs.ingest.download --freeze   # download, (re)write manifest.lock.yaml
    uv run python -m customs.ingest.download --only state_tx,ttb_tax_rates
    uv run python -m customs.ingest.download --from-snapshot /app/snapshot   # Docker: no fetch

Public government sites only; nothing here calls the upgrad endpoints. Downloaded files are data:
never executed or imported. Each body must match its declared format (PDF magic bytes, XML,
JSON, HTML). The lock keeps the raw sha256 and a sha256 of the normalised extracted text;
verification compares the text hash, so a changed page banner doesn't break the build but a
changed rule does (plan §5.2). PDFs are pinned releases, so their text hash is the raw hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

from customs.config import get_settings
from customs.ingest.manifest import (
    LOCK_NAME,
    LockEntry,
    ManifestLock,
    Source,
    load_exclusions,
    load_lock,
    load_manifest,
)
from customs.ingest.parsers import extract_text

# A generic browser-like agent: some agency sites refuse unknown clients. No contact details.
USER_AGENT = "Mozilla/5.0 (compatible; customs-corpus-fetch/0.1)"
RETRY_DELAYS_S = (2.0, 5.0, 10.0)  # government hosts drop connections now and then
PAUSE_S = 0.5  # between requests, to stay polite


class DownloadError(RuntimeError):
    pass


def corpus_dir() -> Path:
    return get_settings().pack_dir / "corpus"


def raw_dir() -> Path:
    return get_settings().data_dir / "raw" / "customs"


def check_format(src: Source, body: bytes) -> None:
    head = body[:2048].lstrip()
    if src.format == "pdf" and not body.startswith(b"%PDF-"):
        raise DownloadError(f"{src.url}: not a PDF (magic bytes missing)")
    if src.format == "xml" and not head.startswith(b"<?xml") and not head.startswith(b"<"):
        raise DownloadError(f"{src.url}: not XML")
    if src.format == "json":
        try:
            json.loads(body)
        except ValueError as err:
            raise DownloadError(f"{src.url}: not JSON ({err})") from err
    if src.format == "html" and b"<html" not in head.lower() and b"<!doctype" not in head.lower():
        raise DownloadError(f"{src.url}: not HTML")


def fetch(client: httpx.Client, src: Source) -> bytes:
    """Network errors are retried; a bad status or a wrong body type is not."""
    for attempt, delay in enumerate((*RETRY_DELAYS_S, None), start=1):
        try:
            resp = client.get(src.url)
            if resp.status_code != 200:
                raise DownloadError(f"{src.url}: HTTP {resp.status_code}")
            check_format(src, resp.content)
            return resp.content
        except httpx.TransportError as err:
            if delay is None:
                raise DownloadError(f"{src.url}: {err}") from err
            print(
                f"     retry {attempt}/{len(RETRY_DELAYS_S)} after {delay:.0f}s: {src.id} ({err})"
            )
            time.sleep(delay)
    raise AssertionError("unreachable")


def hashes(src: Source, body: bytes) -> tuple[str, str]:
    raw_sha = hashlib.sha256(body).hexdigest()
    if src.format == "pdf":
        return raw_sha, raw_sha
    text = extract_text(src, body)
    return raw_sha, hashlib.sha256(text.encode("utf-8")).hexdigest()


def run(
    freeze: bool,
    only: set[str] | None = None,
    client: httpx.Client | None = None,
    snapshot: Path | None = None,
) -> int:
    """With `snapshot` (a raw/ directory, e.g. the host's, mounted read-only in Docker), nothing
    is fetched; each file is verified exactly like a download (the lock's normalised-text
    hash), so the rebuilt chunks are the ones the evaluation used, and government sites that
    block bulk fetches from containers (cbp.gov, abc.ca.gov: HTTP 403) are not hit."""
    if snapshot is not None and freeze:
        print("--from-snapshot cannot --freeze", file=sys.stderr)
        return 2
    cdir = corpus_dir()
    manifest = load_manifest(cdir / "manifest.yaml")
    exclusions = load_exclusions(cdir / "exclusions.yaml")
    lock_path = cdir / LOCK_NAME
    lock = load_lock(lock_path)
    if lock is None and not freeze:
        print(f"No {LOCK_NAME} yet. Run with --freeze to create it.", file=sys.stderr)
        return 2
    if only and freeze and lock is None:
        print("--only with --freeze needs an existing lock to update.", file=sys.stderr)
        return 2

    out = raw_dir()
    out.mkdir(parents=True, exist_ok=True)
    entries: dict[str, LockEntry] = dict(lock.files) if lock is not None else {}
    failures: list[str] = []
    now = datetime.now(UTC).isoformat(timespec="seconds")
    own_client = client is None
    client = client or httpx.Client(  # unused with a snapshot
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        follow_redirects=True,
        timeout=120.0,
    )
    try:
        for src in manifest.sources:
            if only and src.id not in only:
                continue
            if src.language != "en":
                failures.append(f"{src.id}: language '{src.language}' is not allowed")
                continue
            hit = exclusions.match(src.url)
            if hit:
                failures.append(f"{src.id}: {src.url} matches exclusion '{hit}'")
                continue
            try:
                if snapshot is not None:
                    body = (snapshot / "customs" / f"{src.id}{src.suffix}").read_bytes()
                    check_format(src, body)
                else:
                    body = fetch(client, src)
                raw_sha, text_sha = hashes(src, body)
            except Exception as err:  # noqa: BLE001 - every source failure is reported, not fatal
                failures.append(f"{src.id}: {err}")
                continue
            (out / f"{src.id}{src.suffix}").write_bytes(body)
            if lock is not None and not freeze:
                expected = lock.files.get(src.id)
                if expected is None:
                    failures.append(f"{src.id}: missing from {LOCK_NAME}")
                elif expected.text_sha256 != text_sha:
                    failures.append(
                        f"{src.id}: content changed (lock {expected.text_sha256[:12]}…, "
                        f"got {text_sha[:12]}…); re-check the source, then --freeze"
                    )
            entries[src.id] = LockEntry(
                url=src.url,
                sha256=raw_sha,
                text_sha256=text_sha,
                bytes=len(body),
                retrieved_at=now,
            )
            print(f"ok   {src.id:32s} {len(body):>10,d} B  text {text_sha[:12]}…")
            if snapshot is None:
                time.sleep(PAUSE_S)
    finally:
        if own_client:
            client.close()

    if freeze and not failures:
        ids = [s.id for s in manifest.sources]
        new_lock = ManifestLock(files={k: entries[k] for k in ids if k in entries})
        header = (
            "# Generated by `python -m customs.ingest.download --freeze`. Do not hand-edit.\n"
            "# Raw sha256 and normalised-text sha256 of each source in manifest.yaml.\n"
        )
        lock_path.write_text(
            header + yaml.safe_dump(new_lock.model_dump(), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        print(f"wrote {lock_path}")
    elif freeze:
        print(f"lock NOT written: {len(failures)} source(s) failed", file=sys.stderr)

    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--freeze", action="store_true", help="write manifest.lock.yaml")
    parser.add_argument("--only", help="comma-separated source ids")
    parser.add_argument("--from-snapshot", type=Path, help="copy and verify a raw/ dir; no fetch")
    args = parser.parse_args()
    only = set(args.only.split(",")) if args.only else None
    sys.exit(run(freeze=args.freeze, only=only, snapshot=args.from_snapshot))


if __name__ == "__main__":
    main()
