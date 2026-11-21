"""Saved dense index: chunk vectors on disk, so a run never has to re-embed the corpus.

    uv run python -m src.retrieval.index            # build (or confirm) the index for corpus/chunks.jsonl
    uv run python -m src.retrieval.index --rebuild  # embed every chunk again

Files in data/rag-corpus/index/ (git-ignored; rebuild with the command above, SETUP.md step 9):
  vectors.npy   float32, one L2-normalised row per chunk, same order as chunks.jsonl
  meta.json     embedding model, dimension, chunk count, fingerprint of the chunk ids + texts

The fingerprint ties the vectors to one exact chunk set: if the corpus is re-chunked, the saved
index no longer matches and is rebuilt instead of silently pairing vectors with the wrong text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from src.retrieval.corpus import CORPUS, load_chunks

INDEX_DIR = CORPUS / "index"

EmbedFn = Callable[[Sequence[str]], list[list[float]]]


class IndexMismatch(Exception):
    """The saved index was built for other chunks or another embedding model."""


def fingerprint(chunks: Sequence[dict]) -> str:
    h = hashlib.sha256()
    for c in chunks:
        h.update(c["chunk_id"].encode())
        h.update(b"\0")
        h.update(hashlib.sha256(c["text"].encode()).digest())
    return h.hexdigest()


def normalise(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    return m / np.clip(np.linalg.norm(m, axis=1, keepdims=True), 1e-12, None)


def save_index(
    chunks: Sequence[dict],
    matrix: np.ndarray,
    embed_model: str,
    index_dir: Path = INDEX_DIR,
) -> Path:
    if matrix.shape[0] != len(chunks):
        raise ValueError(f"{matrix.shape[0]} vectors for {len(chunks)} chunks")
    index_dir.mkdir(parents=True, exist_ok=True)
    np.save(index_dir / "vectors.npy", normalise(matrix))
    meta = {
        "embed_model": embed_model,
        "dim": int(matrix.shape[1]),
        "n_chunks": len(chunks),
        "fingerprint": fingerprint(chunks),
        "max_chunk_tokens": max((c.get("tokens") or 0) for c in chunks),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (index_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return index_dir


def load_index(
    chunks: Sequence[dict], embed_model: str, index_dir: Path = INDEX_DIR
) -> np.ndarray:
    """The saved vectors for exactly these chunks and this embedding model."""
    meta_path, vec_path = index_dir / "meta.json", index_dir / "vectors.npy"
    if not (meta_path.exists() and vec_path.exists()):
        raise FileNotFoundError(f"no saved index in {index_dir}")
    meta = json.loads(meta_path.read_text())
    if meta.get("embed_model") != embed_model:
        raise IndexMismatch(
            f"index built with {meta.get('embed_model')!r}, not {embed_model!r}"
        )
    if meta.get("fingerprint") != fingerprint(chunks):
        raise IndexMismatch(
            "index was built for a different chunk set (corpus re-chunked?)"
        )
    m = np.load(vec_path)
    if m.shape != (meta["n_chunks"], meta["dim"]):
        raise IndexMismatch(f"vectors.npy shape {m.shape} does not match meta.json")
    return m


def build_index(
    chunks: Sequence[dict],
    embed: EmbedFn,
    embed_model: str,
    index_dir: Path = INDEX_DIR,
) -> np.ndarray:
    m = np.asarray(embed([c["text"] for c in chunks]), dtype=np.float32)
    save_index(chunks, m, embed_model, index_dir)
    return np.load(index_dir / "vectors.npy")  # exactly what a later run will load


def load_or_build(
    chunks: Sequence[dict],
    embed: EmbedFn,
    embed_model: str,
    index_dir: Path = INDEX_DIR,
    log: Callable[[str], None] = print,
) -> np.ndarray:
    try:
        return load_index(chunks, embed_model, index_dir)
    except (FileNotFoundError, IndexMismatch) as e:
        log(f"retrieval index: {e}; embedding {len(chunks)} chunks (one-off)")
        return build_index(chunks, embed, embed_model, index_dir)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rebuild", action="store_true", help="embed every chunk again")
    args = ap.parse_args()

    from src.llm import LLM

    chunks = load_chunks()
    llm = LLM.from_env(run_name="build_index")
    embed = lambda texts: llm.embed(texts, stage="retrieval_index")  # noqa: E731
    t0 = time.perf_counter()
    if args.rebuild:
        build_index(chunks, embed, llm.embed_model)
    else:
        load_or_build(chunks, embed, llm.embed_model)
    meta = json.loads((INDEX_DIR / "meta.json").read_text())
    print(
        f"index OK: {meta['n_chunks']} chunks x {meta['dim']} dims, {meta['embed_model']}, "
        f"largest chunk {meta['max_chunk_tokens']} tokens, built {meta['built_at']} "
        f"({time.perf_counter() - t0:.0f} s) -> {INDEX_DIR.relative_to(CORPUS.parents[1])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
