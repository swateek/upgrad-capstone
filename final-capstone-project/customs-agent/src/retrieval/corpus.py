"""Load chunks: from corpus/chunks.jsonl, or rebuilt from corpus/docs at another chunk size."""

from __future__ import annotations

import importlib.util
import json
import sys
from functools import lru_cache
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[2] / "data" / "rag-corpus"


@lru_cache(maxsize=1)
def _chunker():
    spec = importlib.util.spec_from_file_location(
        "chunk_corpus", CORPUS / "chunk_corpus.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["chunk_corpus"] = mod
    spec.loader.exec_module(mod)
    return mod


def load_chunks(path: Path | None = None) -> list[dict]:
    """The default chunks (350 tokens) written by chunk_corpus.py."""
    path = path or CORPUS / "corpus" / "chunks.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found: build the corpus first (SETUP.md step 5)"
        )
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def build_chunks(max_tokens: int, docs_dir: Path | None = None) -> list[dict]:
    """Chunk every document in corpus/docs at `max_tokens` (same rules as chunk_corpus.py)."""
    docs_dir = docs_dir or CORPUS / "corpus" / "docs"
    files = sorted(docs_dir.glob("*.md"))
    if not files:
        raise FileNotFoundError(
            f"no documents in {docs_dir}: build the corpus first (SETUP.md step 5)"
        )
    cc = _chunker()
    return [c for f in files for c in cc.chunk_file(f, max_tokens)]
