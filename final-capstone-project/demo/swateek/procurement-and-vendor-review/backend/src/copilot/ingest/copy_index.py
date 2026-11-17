"""Copy Qdrant collections from the embedded store (data/qdrant) to a Qdrant server, vectors
and payloads as they are. No embedding calls: use it to fill Docker's Qdrant from an index that
was already built on the host.

    uv run python -m copilot.ingest.copy_index --to http://localhost:3402            # every collection
    uv run python -m copilot.ingest.copy_index --to http://localhost:3402 --only <name> ...

A collection that already exists on the server is left alone unless --replace is given.
"""

from __future__ import annotations

import argparse
import sys

from qdrant_client import QdrantClient, models

from copilot.config import get_settings

BATCH = 256


def copy_collection(src: QdrantClient, dst: QdrantClient, name: str) -> int:
    info = src.get_collection(name)
    vectors = info.config.params.vectors
    dst.create_collection(
        name,
        vectors_config=models.VectorParams(size=vectors.size, distance=vectors.distance),
    )
    dst.create_payload_index(
        name, field_name="doc_id", field_schema=models.PayloadSchemaType.KEYWORD
    )
    offset, n = None, 0
    while True:
        points, offset = src.scroll(
            name, limit=BATCH, offset=offset, with_payload=True, with_vectors=True
        )
        if points:
            dst.upsert(
                name,
                points=[
                    models.PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in points
                ],
            )
            n += len(points)
        if offset is None:
            return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--to", required=True, help="Qdrant server URL, e.g. http://localhost:3402")
    ap.add_argument("--only", nargs="*", help="collection names (default: all)")
    ap.add_argument("--replace", action="store_true", help="overwrite collections on the server")
    args = ap.parse_args()
    settings = get_settings()
    src = QdrantClient(path=str(settings.data_dir / "qdrant"))
    dst = QdrantClient(url=args.to)
    names = args.only or sorted(c.name for c in src.get_collections().collections)
    for name in names:
        if dst.collection_exists(name):
            if not args.replace:
                print(f"skip {name}: already on the server (use --replace to overwrite)")
                continue
            dst.delete_collection(name)
        n = copy_collection(src, dst, name)
        print(f"copied {name}: {n} points (server count {dst.count(name).count})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
