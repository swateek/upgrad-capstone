"""Alternative chunkings for the chunking experiment (Track B: compare three strategies).

    uv run python -m copilot.ingest.rechunk                 # all alternative chunkers in domain.yaml

Input is the by_rule chunk file, so every chunker sees the same cleaned, PII-scrubbed text and
only the boundaries differ:
  fixed_<N>      sliding windows of N tokens with N/8 overlap, ignoring structure
  recursive_<N>  RecursiveCharacterTextSplitter (paragraph > line > sentence > word), N tokens max
Each chunk records every rule it overlaps (`citations`, largest overlap first) so recall can be
measured at rule level for all chunkers; `citation` is the largest-overlap rule.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import OrderedDict
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from copilot.config import get_settings
from copilot.domains.loader import load_domain
from copilot.llm.budget import get_tokenizer

HEADER = re.compile(r"^\[[^\]]+\]\n?")
SPEC = re.compile(r"^(fixed|recursive)_(\d+)$")


def load_docs(by_rule: Path) -> OrderedDict[str, dict]:
    """doc_id -> {text, spans: [(start, end, citation)], meta} in original order."""
    docs: OrderedDict[str, dict] = OrderedDict()
    with by_rule.open(encoding="utf-8") as fh:
        for c in map(json.loads, fh):
            d = docs.setdefault(
                c["doc_id"],
                {
                    "text": "",
                    "spans": [],
                    "meta": {k: c[k] for k in ("instrument", "edition_date", "synthetic")},
                },
            )
            body = HEADER.sub("", c["text"], count=1).strip()
            if d["text"]:
                d["text"] += "\n\n"
            start = len(d["text"])
            d["text"] += body
            d["spans"].append((start, len(d["text"]), c["citation"]))
    return docs


def overlaps(spans, start: int, end: int) -> list[str]:
    weight: dict[str, int] = {}
    for s, e, cit in spans:
        ov = min(e, end) - max(s, start)
        if ov > 0:
            weight[cit] = weight.get(cit, 0) + ov
    return [c for c, _ in sorted(weight.items(), key=lambda kv: -kv[1])]


def fixed_windows(text: str, size: int, tok) -> list[tuple[int, int]]:
    enc = tok.encode(text)
    offsets = enc.offsets
    step = size - size // 8
    out = []
    for i in range(0, max(len(offsets), 1), step):
        window = offsets[i : i + size]
        if not window:
            break
        out.append((window[0][0], window[-1][1]))
        if i + size >= len(offsets):
            break
    return out


def recursive_spans(text: str, size: int, tok) -> list[tuple[int, int]]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=size // 10,
        length_function=lambda t: len(tok.encode(t).ids),
        separators=["\n\n", "\n", ". ", " ", ""],
        add_start_index=True,
    )
    return [
        (d.metadata["start_index"], d.metadata["start_index"] + len(d.page_content))
        for d in splitter.create_documents([text])
    ]


def build(chunker: str, docs, tok, out_dir: Path) -> dict:
    m = SPEC.match(chunker)
    if not m:
        raise SystemExit(f"unknown chunker '{chunker}' (expected fixed_N or recursive_N)")
    kind, size = m.group(1), int(m.group(2))
    rows = []
    for doc_id, d in docs.items():
        spans = (
            fixed_windows(d["text"], size, tok)
            if kind == "fixed"
            else recursive_spans(d["text"], size, tok)
        )
        for n, (s, e) in enumerate(spans, start=1):
            cits = overlaps(d["spans"], s, e)
            text = f"[{doc_id}]\n" + d["text"][s:e]
            primary = cits[0] if cits else f"{doc_id}:?"
            rows.append(
                {
                    "chunk_id": f"{doc_id}:{chunker}:{n}",
                    "citation": primary,
                    "citations": cits,
                    "doc_id": doc_id,
                    "rule_id": primary.split(":", 1)[1],
                    "part": 1,
                    "parts": 1,
                    "title": f"{doc_id} ({chunker} #{n})",
                    "chunker": chunker,
                    "n_tokens": len(tok.encode(text).ids),
                    "text": text,
                    **d["meta"],
                }
            )
    path = out_dir / f"{chunker}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    toks = [r["n_tokens"] for r in rows]
    return {
        "chunker": chunker,
        "chunks": len(rows),
        "tokens_mean": round(statistics.mean(toks)),
        "tokens_max": max(toks),
        "file": str(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("chunkers", nargs="*")
    args = parser.parse_args()
    settings = get_settings()
    domain = load_domain(settings.domain_dir)
    out_dir = settings.data_dir / "processed" / domain.name / "chunks"
    docs = load_docs(out_dir / "by_rule.jsonl")
    tok = get_tokenizer(settings.tokenizer_id)
    chunkers = args.chunkers or [c for c in domain.corpus.chunkers if c != "by_rule"]
    for c in chunkers:
        info = build(c, docs, tok, out_dir)
        if info["chunks"] > settings.max_corpus_docs:
            print(f"FAIL {c}: {info['chunks']} chunks exceeds the {settings.max_corpus_docs} cap")
            return 1
        print(json.dumps(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
