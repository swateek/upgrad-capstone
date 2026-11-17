"""The indexer, offline: dry run sends nothing, texts are embedded once (cache), collections are
rebuilt only when stale, the quota log is written for real calls. Fake embedder, in-memory Qdrant."""

import json

import pytest
from qdrant_client import QdrantClient

from customs.config import Settings
from customs.ingest import index as ix


class FakeEmbedder:
    def __init__(self):
        self.requests = 0
        self.tokens_used = 0
        self.seen: list[str] = []

    def embed_documents(self, texts):
        self.seen.extend(texts)
        self.requests += -(-len(texts) // 16)
        self.tokens_used += 5 * len(texts)
        return [[float(len(t)), 1.0, 0.5] for t in texts]


def chunk(cid, text, chunker="paragraph"):
    return {
        "chunk_id": cid,
        "chunker": chunker,
        "citation": cid,
        "clause_ids": [cid],
        "doc_id": "src",
        "section_id": "s",
        "title": "t",
        "topic": "exemptions",
        "role": "core",
        "synthetic": False,
        "edition": "e",
        "n_tokens": 5,
        "text": text,
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    s = Settings(_env_file=None, data_dir=tmp_path / "data", upgrad_embed_api_key="k")
    cdir = s.data_dir / "chunks"
    cdir.mkdir(parents=True)
    texts = ["One liter of alcohol.", "Cuban cigars are prohibited.", "One liter of alcohol."]
    for ch in ("paragraph", "section"):
        rows = [chunk(f"{ch}:{i}", t, ch) for i, t in enumerate(texts)]
        (cdir / f"{ch}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (cdir / "corpus.hash").write_text("hash1\n")
    log = tmp_path / "quota-log.md"
    log.write_text("| header |\n")
    monkeypatch.setattr(ix, "QUOTA_LOG", log)
    return s, log, QdrantClient(location=":memory:")


def test_dry_run_sends_nothing(env, capsys):
    s, log, client = env
    fake = FakeEmbedder()
    assert ix.run(["paragraph"], True, False, None, embedder=fake, client=client, settings=s) == 0
    assert fake.requests == 0 and "dry run" in capsys.readouterr().out
    assert log.read_text() == "| header |\n"


def test_each_text_embedded_once_and_logged(env):
    s, log, client = env
    fake = FakeEmbedder()
    ix.run(
        ["paragraph", "section"], False, False, "tester", embedder=fake, client=client, settings=s
    )
    assert sorted(fake.seen) == sorted(["One liter of alcohol.", "Cuban cigars are prohibited."])
    assert fake.requests == 1
    assert "tester" in log.read_text() and "index embeddings" in log.read_text()
    assert client.count("customs__paragraph__bge-small-en-v1-5").count == 3

    again = FakeEmbedder()  # second run: cache hit, collections up to date
    ix.run(
        ["paragraph", "section"], False, False, "tester", embedder=again, client=client, settings=s
    )
    assert again.requests == 0 and log.read_text().count("index embeddings") == 1


def test_from_cache_never_calls_and_fails_if_cache_is_short(env):
    s, _, client = env
    with pytest.raises(ix.IndexBuildError, match="not in the cache"):
        ix.run(["paragraph"], False, True, None, embedder=FakeEmbedder(), client=client, settings=s)


def test_calling_the_endpoint_needs_who(env):
    s, _, client = env
    with pytest.raises(ix.IndexBuildError, match="--who"):
        ix.run(
            ["paragraph"], False, False, None, embedder=FakeEmbedder(), client=client, settings=s
        )


def test_new_corpus_hash_rebuilds_from_cache(env):
    s, _, client = env
    ix.run(["paragraph"], False, False, "t", embedder=FakeEmbedder(), client=client, settings=s)
    (s.data_dir / "chunks" / "corpus.hash").write_text("hash2\n")
    ix.run(["paragraph"], False, True, None, client=client, settings=s)  # cache only, no embedder
    sample, _ = client.scroll("customs__paragraph__bge-small-en-v1-5", limit=1, with_payload=True)
    assert sample[0].payload["corpus_hash"] == "hash2"
    assert sample[0].payload["clause_ids"] and sample[0].payload["topic"] == "exemptions"


def test_long_text_is_split_into_windows():
    text = "duty " * 1200
    assert len(ix.windows(text)) > 1 and ix.windows("short") == ["short"]
