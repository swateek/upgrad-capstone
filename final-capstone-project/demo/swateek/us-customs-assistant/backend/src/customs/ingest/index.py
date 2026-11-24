"""Embed the chunk sets and load them into Qdrant (plan step 7).

    uv run python -m customs.ingest.index --dry-run           # count requests; sends NOTHING
    uv run python -m customs.ingest.index --who swateek       # embed + index (calls upgrad!)
    uv run python -m customs.ingest.index --chunker paragraph --who swateek
    uv run python -m customs.ingest.index --from-cache        # index from the cache only (0 calls)

Calling the upgrad embedding endpoint needs the user's explicit OK (AGENTS.md); --dry-run and
--from-cache never call it.

- One Qdrant collection per chunker: customs__<chunker>__bge-small-en-v1-5. Each point carries
  the embedding model and the corpus hash; a collection built from another corpus or model is
  rebuilt, an up-to-date one is skipped.
- Embedding cache (data/embeddings/<model>.jsonl): one vector per distinct text window, keyed by
  sha256. A text is sent to the endpoint at most once, ever; later rebuilds (another chunker,
  Docker, a fresh Qdrant) read the cache.
- Each run that reaches the endpoint appends a line to docs/quota-log.md (requests, tokens).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from customs.config import PROJECT_ROOT, Settings, get_settings
from customs.ingest.build_chunks import CHUNKERS
from customs.llm.budget import get_tokenizer
from customs.llm.endpoints import BGE_TOKENIZER, EMBED_BATCH, EMBED_MAX_TOKENS
from customs.retrieval.dense import DenseStore, StaleIndex, collection_name, make_client
from customs.retrieval.embed import WINDOW_MARGIN, WINDOW_OVERLAP

QUOTA_LOG = PROJECT_ROOT / "docs" / "quota-log.md"


class IndexBuildError(RuntimeError):
    pass


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def windows(text: str) -> list[str]:
    """Same windowing as customs.retrieval.embed.Embedder.windows, without an endpoint."""
    tok = get_tokenizer(BGE_TOKENIZER)
    window = EMBED_MAX_TOKENS - WINDOW_MARGIN
    enc = tok.encode(text, add_special_tokens=False)
    n = len(enc.ids)
    if n <= window:
        return [text]
    out, start, step = [], 0, window - WINDOW_OVERLAP
    while True:
        end = min(start + window, n)
        out.append(text[enc.offsets[start][0] : enc.offsets[end - 1][1]])
        if end == n:
            return out
        start += step


class EmbeddingCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.vectors: dict[str, list[float]] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.vectors[row["sha"]] = row["v"]

    def missing(self, texts: list[str]) -> list[str]:
        seen, out = set(), []
        for t in texts:
            h = sha(t)
            if h not in self.vectors and h not in seen:
                seen.add(h)
                out.append(t)
        return out

    def add(self, texts: list[str], vectors: list[list[float]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            for t, v in zip(texts, vectors, strict=True):
                h = sha(t)
                if h not in self.vectors:
                    self.vectors[h] = v
                    fh.write(json.dumps({"sha": h, "v": v}) + "\n")

    def get(self, text: str) -> list[float]:
        return self.vectors[sha(text)]


def load_chunks(settings: Settings, chunker: str) -> tuple[list[dict], str]:
    cdir = settings.data_dir / "chunks"
    path = cdir / f"{chunker}.jsonl"
    hpath = cdir / "corpus.hash"
    if not path.exists() or not hpath.exists():
        raise IndexBuildError(f"{path} missing: run customs.ingest.build_chunks first")
    chunks = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
    return chunks, hpath.read_text(encoding="utf-8").strip()


def plan(settings: Settings, chunkers: list[str], cache: EmbeddingCache) -> dict:
    """What a run would send: texts not in the cache, per chunker and in total."""
    todo: list[str] = []
    queued: set[str] = set()
    per: dict[str, dict] = {}
    for ch in chunkers:
        chunks, _ = load_chunks(settings, ch)
        texts = [w for c in chunks for w in windows(c["text"])]
        new = [t for t in cache.missing(texts) if t not in queued]
        queued.update(new)
        todo.extend(new)
        per[ch] = {"chunks": len(chunks), "windows": len(texts), "new_windows": len(new)}
    return {"per_chunker": per, "texts": todo, "requests": -(-len(todo) // EMBED_BATCH)}


def append_quota_log(
    who: str, what: str, chat_requests: int, embed_requests: int, tokens: int, notes: str
) -> None:
    line = (
        f"| {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} | {who} | {what} | {chat_requests} "
        f"| {embed_requests} | {tokens} | {notes} |\n"
    )
    with QUOTA_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line)


def run(
    chunkers: list[str],
    dry_run: bool,
    from_cache: bool,
    who: str | None,
    embedder=None,
    client=None,
    settings: Settings | None = None,
) -> int:
    settings = settings or get_settings()
    model = settings.embedding_model
    cache = EmbeddingCache(settings.data_dir / "embeddings" / f"{model.replace('.', '-')}.jsonl")
    p = plan(settings, chunkers, cache)
    for ch, v in p["per_chunker"].items():
        print(f"{ch:10s} chunks={v['chunks']:5d} windows={v['windows']:5d} new={v['new_windows']}")
    print(f"to embed: {len(p['texts'])} texts in {p['requests']} requests of <= {EMBED_BATCH}")
    if dry_run:
        print("dry run: nothing sent")
        return 0
    if p["texts"]:
        if from_cache:
            raise IndexBuildError(f"--from-cache, but {len(p['texts'])} texts are not in the cache")
        if not who:
            raise IndexBuildError("calling the upgrad embedding endpoint needs --who (quota log)")
        if embedder is None:
            from customs.retrieval.embed import Embedder

            embedder = Embedder(settings)
        before_req, before_tok = embedder.requests, embedder.tokens_used
        vectors = embedder.embed_documents(p["texts"])
        cache.add(p["texts"], vectors)
        sent = embedder.requests - before_req
        append_quota_log(
            who,
            f"index embeddings ({', '.join(chunkers)})",
            0,
            sent,
            embedder.tokens_used - before_tok,
            f"{len(p['texts'])} new texts; cache now {len(cache.vectors)}",
        )
        print(f"embedded {len(p['texts'])} texts in {sent} requests")

    client = client or make_client(settings)
    for ch in chunkers:
        chunks, corpus_hash = load_chunks(settings, ch)
        store = DenseStore(client, collection_name(ch, model))
        try:
            n = store.check(model, corpus_hash)
            print(f"{store.collection}: up to date ({n} points), skipped")
            continue
        except StaleIndex as err:
            print(f"{store.collection}: {err}; rebuilding")
        vectors = [[cache.get(w) for w in windows(c["text"])] for c in chunks]
        dim = len(vectors[0][0])
        store.recreate(dim)
        store.upsert(chunks, vectors, model, corpus_hash)
        print(f"{store.collection}: {store.check(model, corpus_hash)} points ({dim} dims)")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chunker", choices=CHUNKERS, action="append")
    parser.add_argument("--dry-run", action="store_true", help="count requests; send nothing")
    parser.add_argument("--from-cache", action="store_true", help="never call the endpoint")
    parser.add_argument("--who", help="who ran it (quota log); required to call the endpoint")
    args = parser.parse_args()
    try:
        sys.exit(run(args.chunker or list(CHUNKERS), args.dry_run, args.from_cache, args.who))
    except IndexBuildError as err:
        print(f"FAIL {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
