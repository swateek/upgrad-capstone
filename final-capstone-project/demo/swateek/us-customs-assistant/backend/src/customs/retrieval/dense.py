"""Dense vectors in Qdrant: embedded (local path) for dev/eval, server (QDRANT_URL) in Docker.

One collection per chunker and query-prefix setting: "customs__<chunker>__bge-small-en-v1-5",
so the chunking variants of the retrieval experiment stay built side by side.
Every point's payload carries the embedding model and corpus hash; `check()` refuses to serve an
index built from a different corpus or model. A chunk may have several points (one per window,
when the embedding endpoint takes fewer tokens than the chunk has); search keeps the best one.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from qdrant_client import QdrantClient, models

from customs.config import Settings


class StaleIndex(RuntimeError):
    pass


@dataclass(frozen=True)
class DenseHit:
    chunk_id: str
    citation: str
    score: float


def collection_name(chunker: str, embedding_model: str = "bge-small-en-v1.5") -> str:
    return f"customs__{chunker}__{embedding_model.replace('.', '-')}"


def make_client(settings: Settings) -> QdrantClient:
    if settings.qdrant_url:
        return QdrantClient(url=settings.qdrant_url)
    path: Path = settings.data_dir / "qdrant"
    path.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(path))


def point_id(chunk_id: str, window: int = 0) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id if window == 0 else f"{chunk_id}#{window}"))


class DenseStore:
    def __init__(self, client: QdrantClient, collection: str) -> None:
        self.client = client
        self.collection = collection

    def recreate(self, dim: int) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection,
            vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
        )
        if not getattr(self.client, "_client", None).__class__.__name__.startswith("QdrantLocal"):
            # payload indexes only matter on the server; embedded mode filters by scanning
            self.client.create_payload_index(
                self.collection, field_name="doc_id", field_schema=models.PayloadSchemaType.KEYWORD
            )

    def upsert(
        self,
        chunks: Sequence[dict],
        vectors: Sequence[Sequence[Sequence[float]]],
        embedding_model: str,
        corpus_hash: str,
    ) -> None:
        """vectors[i] holds chunk i's vectors, one per window (usually one)."""
        points = [
            models.PointStruct(
                id=point_id(c["chunk_id"], w),
                vector=list(v),
                payload={
                    "chunk_id": c["chunk_id"],
                    "citation": c["citation"],
                    "doc_id": c["doc_id"],
                    "topic": c.get("topic"),
                    "window": w,
                    "embedding_model": embedding_model,
                    "corpus_hash": corpus_hash,
                },
            )
            for c, vs in zip(chunks, vectors, strict=True)
            for w, v in enumerate(vs)
        ]
        for i in range(0, len(points), 256):
            self.client.upsert(self.collection, points=points[i : i + 256])

    def check(self, embedding_model: str, corpus_hash: str) -> int:
        """Raise StaleIndex unless the collection matches; return its point count."""
        if not self.client.collection_exists(self.collection):
            raise StaleIndex(f"collection {self.collection} does not exist; run the indexer")
        sample, _ = self.client.scroll(self.collection, limit=1, with_payload=True)
        if not sample:
            raise StaleIndex(f"collection {self.collection} is empty")
        p = sample[0].payload or {}
        if p.get("embedding_model") != embedding_model or p.get("corpus_hash") != corpus_hash:
            raise StaleIndex(
                f"{self.collection} was built with {p.get('embedding_model')} / corpus "
                f"{str(p.get('corpus_hash'))[:12]}; expected {embedding_model} / {corpus_hash[:12]}"
            )
        return self.client.count(self.collection).count

    def search(
        self, vector: Sequence[float], k: int, doc_ids: set[str] | None = None
    ) -> list[DenseHit]:
        flt = (
            models.Filter(
                must=[
                    models.FieldCondition(key="doc_id", match=models.MatchAny(any=sorted(doc_ids)))
                ]
            )
            if doc_ids
            else None
        )
        # over-fetch, then keep each chunk's best window (points come back best first)
        res = self.client.query_points(
            self.collection, query=list(vector), limit=k * 3, query_filter=flt, with_payload=True
        )
        hits: dict[str, DenseHit] = {}
        for p in res.points:
            cid = p.payload["chunk_id"]
            if cid not in hits:
                hits[cid] = DenseHit(cid, p.payload["citation"], float(p.score))
        return list(hits.values())[:k]
