"""Embed a chunk set and load it into Qdrant (dense half of hybrid retrieval).

    uv run python -m copilot.ingest.index                 # active chunker (CHUNKER, default by_rule)
    uv run python -m copilot.ingest.index --force         # rebuild even if up to date

Indexes for the active provider (PROVIDER in .env): its embedding model, its own collection.
Run once per provider; both indexes stay side by side. Skips work when the collection already
matches the chunk file's hash and the embedding model. BM25 needs no index step: it is built in
memory from the same chunk file at startup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from copilot.config import get_settings
from copilot.domains.loader import load_domain
from copilot.llm.providers import get_embedding
from copilot.retrieval.dense import DenseStore, StaleIndex, collection_name, make_client
from copilot.retrieval.embed import Embedder


def chunks_path(data_dir: Path, domain: str, chunker: str) -> Path:
    return data_dir / "processed" / domain / "chunks" / f"{chunker}.jsonl"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chunker")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    domain = load_domain(settings.domain_dir)
    chunker = args.chunker or settings.chunker
    path = chunks_path(settings.data_dir, domain.name, chunker)
    if not path.exists():
        print(f"FAIL {path} missing; run copilot.ingest.build_chunks first", file=sys.stderr)
        return 1
    corpus_hash = file_hash(path)
    emb = get_embedding(settings)
    model = emb.model
    store = DenseStore(
        make_client(settings), collection_name(domain.name, chunker, emb.collection_suffix)
    )

    if not args.force:
        try:
            n = store.check(model, corpus_hash)
            print(
                f"up to date: {store.collection} ({n} points, {model}, corpus {corpus_hash[:12]})"
            )
            return 0
        except StaleIndex as why:
            print(f"rebuilding: {why}")

    with path.open(encoding="utf-8") as fh:
        chunks = [json.loads(x) for x in fh]
    embedder = Embedder(settings)
    t0 = time.perf_counter()
    vectors = embedder.embed_chunks([c["text"] for c in chunks])
    store.recreate(len(vectors[0][0]))
    store.upsert(chunks, vectors, model, corpus_hash)
    n = store.check(model, corpus_hash)
    meta = {
        "provider": settings.provider,
        "collection": store.collection,
        "embedding_model": model,
        "dimensions": len(vectors[0][0]),
        "corpus_hash": corpus_hash,
        "chunks": len(chunks),
        "chunks_windowed": sum(len(v) > 1 for v in vectors),
        "points": n,
        "embedding_tokens": embedder.tokens_used,
        "seconds": round(time.perf_counter() - t0, 1),
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    # SiliconFlow keeps the original file name; other providers get their own
    name = "index.json" if settings.provider == "siliconflow" else f"{settings.provider}.index.json"
    out = path.with_name(f"{path.stem}.{name}")
    out.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
