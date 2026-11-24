"""Build the documents and the three chunk sets of the retrieval experiment (plan §6).

    uv run python -m customs.ingest.build_chunks

- verifies every downloaded file against manifest.lock.yaml (text hash) before parsing
- parses each source into documents (one citable unit each; customs.ingest.parsers) and adds
  the synthetic injection fixtures from pack/corpus/synthetic/
- scrubs PII, enforces the 2,000-document cap and refuses excluded URLs
- writes data/chunks/documents.jsonl (clause id -> text, for citations and fetch-by-id) and
  data/chunks/<chunker>.jsonl for:
      paragraph   one chunk per document, with a metadata header (long ones split into parts)
      section     one chunk per section (all its paragraphs), with a header
      window200   200-token windows over each section's text, no header (the naive baseline)
- writes a count report to docs/results/corpus-counts.md

Offline: nothing here calls a model endpoint. Token counts use the bge tokenizer (the
embedding endpoint's limit is 512 bge tokens per text).
"""

from __future__ import annotations

import hashlib
import re
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel

from customs.config import PROJECT_ROOT, get_settings
from customs.ingest.download import hashes, raw_dir
from customs.ingest.manifest import (
    LOCK_NAME,
    Source,
    load_exclusions,
    load_lock,
    load_manifest,
    load_splitting,
)
from customs.ingest.parsers import Document, parse, parse_markdown
from customs.ingest.pii import scrub
from customs.llm.budget import get_tokenizer
from customs.llm.endpoints import BGE_TOKENIZER

CHUNKERS = ("paragraph", "section", "window200")
SECTION_MAX_TOKENS = 1200
WINDOW_TOKENS = 200
WINDOW_STRIDE = 160
TARGET_DOCS = (500, 2000)


class CorpusError(RuntimeError):
    pass


class DocRecord(BaseModel):
    doc_id: str  # clause id, e.g. "cfr19_p148:148.33(a)"
    citation: str
    source_id: str
    section_id: str
    title: str
    topic: str
    role: str
    synthetic: bool
    n_tokens: int
    text: str


class Chunk(BaseModel):
    chunk_id: str
    chunker: str
    citation: str
    clause_ids: list[str]
    doc_id: str  # the source id (Qdrant payload filter key, as in the reference app)
    section_id: str
    title: str
    topic: str
    role: str
    synthetic: bool
    edition: str
    n_tokens: int
    text: str


def load_synthetic(sdir: Path, prefix: str) -> list[tuple[dict, list[Document]]]:
    out = []
    for md in sorted(p for p in sdir.glob("*.md") if p.name != "README.md"):
        text = md.read_text(encoding="utf-8")
        if not text.startswith("---"):
            raise CorpusError(f"{md.name}: synthetic docs need YAML front matter")
        _, front, body = text.split("---", 2)
        meta = yaml.safe_load(front)
        if meta.get("synthetic") is not True or not meta.get("id"):
            raise CorpusError(f"{md.name}: front matter needs id and synthetic: true")
        docs = parse_markdown(meta["id"], f"{prefix}: {meta.get('title', meta['id'])}", body)
        out.append((meta, docs))
    return out


RESERVED = re.compile(r"^(\([a-z0-9]+\)\s*)?\[Reserved\]\.?$", re.IGNORECASE)
REDACTION = re.compile(r"\[REDACTED-[A-Z]+\]")
MIN_REAL_CHARS = 25


def is_empty(text: str) -> bool:
    """Reserved paragraphs and blocks with almost no real text (after PII redaction)."""
    real = REDACTION.sub("", text).strip()
    return bool(RESERVED.match(real)) or len(real) < MIN_REAL_CHARS


def split_parts(text: str, count: Callable[[str], int], limit: int) -> list[str]:
    """Split at line boundaries (then words) so every part is at most `limit` tokens."""
    if count(text) <= limit:
        return [text]
    parts, cur = [], []
    for line in text.split("\n"):
        pieces = [line]
        if count(line) > limit:  # one very long line: cut by words
            words, pieces, buf = line.split(" "), [], []
            for w in words:
                if buf and count(" ".join([*buf, w])) > limit:
                    pieces.append(" ".join(buf))
                    buf = []
                buf.append(w)
            if buf:
                pieces.append(" ".join(buf))
        for piece in pieces:
            if cur and count("\n".join([*cur, piece])) > limit:
                parts.append("\n".join(cur))
                cur = []
            cur.append(piece)
    if cur:
        parts.append("\n".join(cur))
    return parts


def build() -> int:
    settings = get_settings()
    cdir = settings.pack_dir / "corpus"
    manifest = load_manifest(cdir / "manifest.yaml")
    exclusions = load_exclusions(cdir / "exclusions.yaml")
    lock = load_lock(cdir / LOCK_NAME)
    if lock is None:
        raise CorpusError(f"{LOCK_NAME} missing; run customs.ingest.download --freeze")
    specs = load_splitting(cdir / "splitting.yaml")
    synth_prefix = (
        yaml.safe_load((cdir / "splitting.yaml").read_text(encoding="utf-8"))
        .get("synthetic", {})
        .get("citation_prefix", "Synthetic fixture")
    )
    tok = get_tokenizer(BGE_TOKENIZER)

    def count(text: str) -> int:
        return len(tok.encode(text, add_special_tokens=False).ids)

    rdir = raw_dir()
    records: list[DocRecord] = []
    meta_of: dict[str, dict] = {}
    per_source: dict[str, dict] = {}
    pii_total: Counter[str] = Counter()

    dropped: list[str] = []

    def add(meta: dict, docs: list[Document]) -> None:
        toks = []
        kept = []
        for d in docs:
            text, found = scrub(d.text)
            if is_empty(text):
                dropped.append(d.doc_id)
                continue
            kept.append(d)
            pii_total.update(found)
            n = count(text)
            toks.append(n)
            records.append(
                DocRecord(
                    doc_id=d.doc_id,
                    citation=d.citation,
                    source_id=d.source_id,
                    section_id=d.section_id,
                    title=d.title,
                    topic=meta["topic"],
                    role=meta["role"],
                    synthetic=meta["synthetic"],
                    n_tokens=n,
                    text=text,
                )
            )
        per_source[meta["id"]] = {
            "title": meta["title"],
            "role": meta["role"],
            "documents": len(kept),
            "sections": len({d.section_id for d in kept}),
            "tokens_mean": round(statistics.mean(toks)) if toks else 0,
            "tokens_max": max(toks, default=0),
        }

    for src in manifest.sources:
        if exclusions.match(src.url):
            raise CorpusError(f"{src.id}: {src.url} is excluded")
        path = rdir / f"{src.id}{src.suffix}"
        expected = lock.files.get(src.id)
        if expected is None or not path.exists():
            raise CorpusError(f"{src.id}: file missing or not in {LOCK_NAME}; run the downloader")
        _, text_sha = hashes(src, path.read_bytes())
        if text_sha != expected.text_sha256:
            raise CorpusError(f"{src.id}: content differs from {LOCK_NAME}")
        spec = specs.get(src.id)
        if spec is None:
            raise CorpusError(f"{src.id}: no entry in splitting.yaml")
        meta = _meta(src)
        meta_of[src.id] = meta
        add(meta, parse(src, spec, path))

    for fm, docs in load_synthetic(cdir / "synthetic", synth_prefix):
        meta = {
            "id": fm["id"],
            "title": fm.get("title", fm["id"]),
            "topic": fm.get("topic", "declaring"),
            "role": "injection_fixture",
            "synthetic": True,
            "edition": "synthetic",
        }
        meta_of[fm["id"]] = meta
        add(meta, docs)

    total = len(records)
    if total > settings.max_corpus_docs:
        raise CorpusError(f"{total} documents exceeds the cap of {settings.max_corpus_docs}")
    dupes = [k for k, n in Counter(r.doc_id for r in records).items() if n > 1]
    if dupes:
        raise CorpusError(f"duplicate clause ids, fix the parser or splitting.yaml: {dupes[:10]}")

    out_dir = settings.data_dir / "chunks"
    out_dir.mkdir(parents=True, exist_ok=True)
    docs_path = out_dir / "documents.jsonl"
    docs_blob = "".join(r.model_dump_json() + "\n" for r in records)
    docs_path.write_text(docs_blob, encoding="utf-8")
    corpus_hash = hashlib.sha256(docs_blob.encode("utf-8")).hexdigest()

    chunk_counts: dict[str, dict] = {}
    for chunker in CHUNKERS:
        chunks = list(_chunks(chunker, records, meta_of, count, specs))
        path = out_dir / f"{chunker}.jsonl"
        path.write_text("".join(c.model_dump_json() + "\n" for c in chunks), encoding="utf-8")
        toks = [c.n_tokens for c in chunks]
        chunk_counts[chunker] = {
            "chunks": len(chunks),
            "tokens_mean": round(statistics.mean(toks)),
            "tokens_max": max(toks),
            "over_512": sum(t > 512 for t in toks),
        }
    (out_dir / "corpus.hash").write_text(corpus_hash + "\n", encoding="utf-8")

    report = _report(per_source, chunk_counts, total, pii_total, corpus_hash, records, dropped)
    rpath = PROJECT_ROOT / "docs" / "results" / "corpus-counts.md"
    rpath.parent.mkdir(parents=True, exist_ok=True)
    rpath.write_text(report, encoding="utf-8")
    print(report)
    print(f"wrote {docs_path}\nwrote {out_dir}/<chunker>.jsonl\nwrote {rpath}")
    return 0


def _meta(src: Source) -> dict:
    return {
        "id": src.id,
        "title": src.title,
        "topic": src.topic,
        "role": src.role,
        "synthetic": False,
        "edition": src.edition,
    }


def _header(citation: str, source_title: str, title: str) -> str:
    return f"[{citation}] {source_title} · {title}"


def _chunks(chunker, records, meta_of, count, specs):
    groups: dict[tuple[str, str], list[DocRecord]] = defaultdict(list)
    for r in records:
        groups[(r.source_id, r.section_id)].append(r)

    for (source_id, section_id), docs in groups.items():
        meta = meta_of[source_id]
        base = {
            "chunker": chunker,
            "doc_id": source_id,
            "section_id": section_id,
            "topic": meta["topic"],
            "role": meta["role"],
            "synthetic": meta["synthetic"],
            "edition": meta["edition"],
        }
        if chunker == "paragraph":
            for d in docs:
                spec = specs.get(source_id)
                limit = spec.max_tokens if spec else 450
                parts = split_parts(d.text, count, limit)
                for i, part in enumerate(parts, start=1):
                    label = f" (part {i}/{len(parts)})" if len(parts) > 1 else ""
                    text = _header(d.citation, meta["title"], d.title + label) + "\n" + part
                    yield Chunk(
                        chunk_id=f"paragraph:{d.doc_id}#{i}",
                        citation=d.citation,
                        clause_ids=[d.doc_id],
                        title=d.title,
                        n_tokens=count(text),
                        text=text,
                        **base,
                    )
        elif chunker == "section":
            title = docs[0].title.split(" — ")[0]
            citation = docs[0].citation if len(docs) == 1 else _section_citation(docs)
            header = _header(citation, meta["title"], title)
            for part, batch in enumerate(_section_batches(docs), start=1):
                text = header + "\n" + "\n".join(d.text for d in batch)
                yield Chunk(
                    chunk_id=f"section:{source_id}:{section_id}#{part}",
                    citation=citation,
                    clause_ids=[d.doc_id for d in batch],
                    title=title,
                    n_tokens=count(text),
                    text=text,
                    **base,
                )
        else:  # window200: naive fixed windows over the section text, no header
            text, spans, pos = "", [], 0
            for d in docs:
                spans.append((pos, pos + len(d.text), d))
                text += d.text + "\n"
                pos = len(text)
            enc = TOKENIZER_CACHE.encode(text)
            n, start, w = len(enc.ids), 0, 0
            while start < n:
                end = min(start + WINDOW_TOKENS, n)
                a, b = enc.offsets[start][0], enc.offsets[end - 1][1]
                hits = [d for s, e, d in spans if s < b and e > a]
                w += 1
                yield Chunk(
                    chunk_id=f"window200:{source_id}:{section_id}#{w}",
                    citation=hits[0].citation if hits else source_id,
                    clause_ids=[d.doc_id for d in hits],
                    title=docs[0].title.split(" — ")[0],
                    n_tokens=end - start,
                    text=text[a:b],
                    **base,
                )
                if end == n:
                    break
                start += WINDOW_STRIDE


class _Tok:
    """The bge tokenizer without special tokens (window offsets map back to the text)."""

    def encode(self, text: str):
        return get_tokenizer(BGE_TOKENIZER).encode(text, add_special_tokens=False)


TOKENIZER_CACHE = _Tok()


def _section_batches(docs: list[DocRecord]) -> list[list[DocRecord]]:
    """A section's documents in order, cut into batches of at most SECTION_MAX_TOKENS (a
    single longer document stays whole)."""
    batches: list[list[DocRecord]] = [[]]
    for d in docs:
        if batches[-1] and sum(x.n_tokens for x in batches[-1]) + d.n_tokens > SECTION_MAX_TOKENS:
            batches.append([])
        batches[-1].append(d)
    return batches


def _section_citation(docs: list[DocRecord]) -> str:
    first = docs[0].citation
    # "19 CFR 148.33(a)" -> "19 CFR 148.33"; "OFAC FAQ 719" stays
    return first[: first.rfind("(")] if first.endswith(")") and "(" in first else first


def _report(per_source, chunk_counts, total, pii, corpus_hash, records, dropped) -> str:
    rows = "\n".join(
        f"| `{k}` | {v['role']} | {v['sections']} | {v['documents']} | {v['tokens_mean']} "
        f"| {v['tokens_max']} |"
        for k, v in per_source.items()
    )
    by_role = Counter(r.role for r in records)
    by_topic = Counter(r.topic for r in records)
    crow = "\n".join(
        f"| `{k}` | {v['chunks']} | {v['tokens_mean']} | {v['tokens_max']} | {v['over_512']} |"
        for k, v in chunk_counts.items()
    )
    lo, hi = TARGET_DOCS
    status = "within" if lo <= total <= hi else "OUTSIDE"
    return (
        "# Corpus counts\n\n"
        f"Generated by `python -m customs.ingest.build_chunks` on "
        f"{datetime.now(UTC).date().isoformat()}. One document = one citable unit "
        "(`pack/corpus/splitting.yaml`). Token counts are bge-small tokens.\n\n"
        f"- **Documents: {total}** (Track B range {lo}–{hi}: {status}; hard cap 2,000)\n"
        f"- By role: {dict(by_role)}\n"
        f"- By topic: {dict(by_topic)}\n"
        f"- PII redactions at ingest: {dict(pii) if pii else 'none'} (public agency phone "
        "numbers and email addresses on the pages; no regulation text was affected)\n"
        f"- Dropped as empty (reserved paragraphs, heading-only blocks): {len(dropped)}"
        + (f" ({', '.join(dropped)})" if dropped else "")
        + "\n"
        f"- Corpus hash (documents.jsonl): `{corpus_hash[:16]}…`\n\n"
        "## Per source\n\n"
        "| Source | Role | Sections | Documents | Mean tokens | Max tokens |\n"
        "|---|---|---|---|---|---|\n"
        f"{rows}\n\n"
        "## Chunk sets (retrieval experiment)\n\n"
        "| Chunker | Chunks | Mean tokens | Max tokens | Over 512 (embedded in windows) |\n"
        "|---|---|---|---|---|\n"
        f"{crow}\n"
    )


def main() -> None:
    try:
        sys.exit(build())
    except CorpusError as err:
        print(f"FAIL {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
