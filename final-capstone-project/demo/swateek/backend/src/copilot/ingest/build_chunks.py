"""Build the "by_rule" chunk set for the active domain: one document per rule/heading.

    uv run python -m copilot.ingest.build_chunks

- verifies every source file against manifest.lock.yaml before parsing
- splits policy sources with corpus/splitting.yaml; adds synthetic markdown docs
- adds model_tender sources only if the policy split is under the domain's target minimum
- scrubs PII, enforces the corpus cap, writes data/processed/<domain>/chunks/by_rule.jsonl
  and a count report to docs/results/
"""

from __future__ import annotations

import argparse
import hashlib
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from copilot.config import PROJECT_ROOT, get_settings
from copilot.domains.loader import DomainConfig, load_domain
from copilot.domains.manifest import LOCK_NAME, Source, load_lock, load_manifest
from copilot.ingest.pdf_text import Line, read_pdf_lines
from copilot.ingest.pii import scrub
from copilot.ingest.split import SplitSpec, split_sections, to_pieces
from copilot.llm.budget import get_tokenizer

CHUNKER = "by_rule"


class Chunk(BaseModel):
    chunk_id: str
    citation: str  # "<doc_id>:<rule_id>"
    doc_id: str
    rule_id: str
    part: int
    parts: int
    title: str
    instrument: str
    edition_date: str | None
    page_start: int
    page_end: int
    synthetic: bool
    chunker: str
    n_tokens: int
    text: str


class CorpusError(RuntimeError):
    pass


def load_specs(domain: DomainConfig) -> dict[str, SplitSpec]:
    raw = yaml.safe_load(domain.path(domain.corpus.splitting).read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {})
    return {k: SplitSpec(**{**defaults, **v}) for k, v in raw["sources"].items()}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_synthetic(path: Path) -> tuple[dict[str, Any], list[list[Line]]]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise CorpusError(f"{path.name}: synthetic docs need YAML front matter")
    _, front, body = text.split("---", 2)
    meta = yaml.safe_load(front)
    if meta.get("synthetic") is not True:
        raise CorpusError(f"{path.name}: front matter must say synthetic: true")
    lines = [Line(1, ln) for ln in body.splitlines() if ln.strip()]
    return meta, [lines]


def build(include_model_tender: bool | None) -> int:
    settings = get_settings()
    domain = load_domain(settings.domain_dir)
    manifest_path = domain.path(domain.corpus.manifest)
    manifest = load_manifest(manifest_path)
    lock = load_lock(manifest_path.parent / LOCK_NAME)
    if lock is None:
        raise CorpusError("manifest.lock.yaml missing; run copilot.ingest.download --freeze")
    specs = load_specs(domain)
    tok = get_tokenizer(settings.tokenizer_id)

    def count(text: str) -> int:
        return len(tok.encode(text).ids)

    raw_dir = settings.data_dir / "raw" / domain.name
    chunks: list[Chunk] = []
    pii_total: Counter[str] = Counter()
    per_source: dict[str, dict[str, Any]] = {}

    def add(doc_id: str, instrument: str, edition: str | None, synthetic: bool, pages) -> None:
        spec = specs.get(doc_id)
        if spec is None:
            raise CorpusError(f"{doc_id}: no entry in splitting.yaml")
        sections = split_sections(pages, spec)
        pieces = to_pieces(sections, count, spec.max_tokens)
        toks = []
        for p in pieces:
            header = f"{doc_id}:{p.rule_id} {p.title}".strip()
            if p.parts > 1:
                header += f" (part {p.part}/{p.parts})"
            text, found = scrub(f"[{header}]\n{p.text}")
            pii_total.update(found)
            n = count(text)
            toks.append(n)
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:{p.rule_id}#{p.part}",
                    citation=f"{doc_id}:{p.rule_id}",
                    doc_id=doc_id,
                    rule_id=p.rule_id,
                    part=p.part,
                    parts=p.parts,
                    title=p.title,
                    instrument=instrument,
                    edition_date=edition,
                    page_start=p.page_start,
                    page_end=p.page_end,
                    synthetic=synthetic,
                    chunker=CHUNKER,
                    n_tokens=n,
                    text=text,
                )
            )
        per_source[doc_id] = {
            "sections": len(sections),
            "chunks": len(pieces),
            "tokens_mean": round(statistics.mean(toks)) if toks else 0,
            "tokens_max": max(toks, default=0),
        }

    def add_source(src: Source) -> None:
        path = raw_dir / f"{src.id}.pdf"
        expected = lock.files.get(src.id)
        if expected is None or not path.exists() or sha256_of(path) != expected.sha256:
            raise CorpusError(f"{src.id}: file missing or hash differs from {LOCK_NAME}")
        edition = src.edition_date.isoformat() if src.edition_date else None
        add(src.id, src.instrument or src.id, edition, False, read_pdf_lines(path))

    for src in (s for s in manifest.sources if s.store == "policy"):
        add_source(src)

    if domain.corpus.synthetic_dir:
        for md in sorted(domain.path(domain.corpus.synthetic_dir).glob("*.md")):
            meta, pages = read_synthetic(md)
            add(
                meta["doc_id"],
                meta.get("instrument", "synthetic"),
                str(meta.get("edition_date")),
                True,
                pages,
            )

    target_min, target_max = domain.corpus.target_docs
    policy_count = len(chunks)
    use_tender = (
        include_model_tender if include_model_tender is not None else policy_count < target_min
    )
    if use_tender:
        for src in (s for s in manifest.sources if s.store == "model_tender"):
            add_source(src)

    total = len(chunks)
    if total > settings.max_corpus_docs:
        raise CorpusError(f"{total} documents exceeds the cap of {settings.max_corpus_docs}")
    dupes = [k for k, n in Counter(c.chunk_id for c in chunks).items() if n > 1]
    if dupes:
        raise CorpusError(f"duplicate chunk ids, fix splitting.yaml: {dupes[:10]}")

    out_dir = settings.data_dir / "processed" / domain.name / "chunks"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{CHUNKER}.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(c.model_dump_json() + "\n")

    report = _report(
        domain.name,
        per_source,
        policy_count,
        total,
        use_tender,
        pii_total,
        (target_min, target_max),
    )
    rpath = PROJECT_ROOT / "docs" / "results" / f"phase1-corpus-{CHUNKER}.md"
    rpath.parent.mkdir(parents=True, exist_ok=True)
    rpath.write_text(report, encoding="utf-8")
    print(report)
    print(f"wrote {out}\nwrote {rpath}")
    return 0


def _report(domain, per_source, policy_count, total, use_tender, pii, target) -> str:
    rows = "\n".join(
        f"| `{k}` | {v['sections']} | {v['chunks']} | {v['tokens_mean']} | {v['tokens_max']} |"
        for k, v in per_source.items()
    )
    in_range = target[0] <= total <= target[1]
    return (
        f"# Corpus: `{CHUNKER}` chunker ({domain})\n\n"
        "Generated by `python -m copilot.ingest.build_chunks`. One document per rule or heading; "
        "long sections split into parts that share the rule id.\n\n"
        "| Source | Sections | Chunks | Mean tokens | Max tokens |\n|---|---|---|---|---|\n"
        f"{rows}\n\n"
        f"- Policy + synthetic documents: **{policy_count}**\n"
        f"- Model-tender sections included: **{'yes' if use_tender else 'no'}**\n"
        f"- Total documents: **{total}** (target {target[0]}–{target[1]}: "
        f"{'within' if in_range else 'OUTSIDE'}; hard cap 2,000)\n"
        f"- PII redactions: {dict(pii) if pii else 'none'}\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--with-model-tender", dest="tender", action="store_true", default=None)
    group.add_argument("--without-model-tender", dest="tender", action="store_false")
    args = parser.parse_args()
    try:
        sys.exit(build(args.tender))
    except CorpusError as err:
        print(f"FAIL {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
