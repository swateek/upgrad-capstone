"""Retrieval building blocks, offline: RRF, BM25, Qdrant (in memory), listwise parsing,
embedding windows and the embedding request shape (mock endpoint)."""

import json

import httpx
import pytest
from conftest import chat_response, mock_openai
from qdrant_client import QdrantClient

from customs.llm import ChatClient
from customs.retrieval.bm25 import BM25Index
from customs.retrieval.dense import DenseStore, StaleIndex, collection_name
from customs.retrieval.embed import Embedder
from customs.retrieval.hybrid import HybridRetriever, rrf
from customs.retrieval.rerank import ListwiseReranker

CHUNKS = [
    {
        "chunk_id": "c1",
        "citation": "19cfr148:148.33(a)",
        "doc_id": "19cfr148",
        "text": "One liter of alcoholic beverages may be included in the exemption if 21 or older.",
        "n_tokens": 20,
    },
    {
        "chunk_id": "c2",
        "citation": "19cfr148:148.51(b)",
        "doc_id": "19cfr148",
        "text": "No article is exempt if any accompanying article exceeds the $200 limit.",
        "n_tokens": 18,
    },
    {
        "chunk_id": "c3",
        "citation": "31cfr515:515.204",
        "doc_id": "31cfr515",
        "text": "Importation of goods of Cuban origin is prohibited.",
        "n_tokens": 12,
    },
]


def test_rrf_rewards_agreement():
    fused = rrf({"bm25": ["a", "b", "c"], "dense": ["b", "a", "d"]})
    assert [c for c, _, _ in fused][:2] == ["a", "b"] or [c for c, _, _ in fused][:2] == ["b", "a"]
    assert fused[-1][0] in {"c", "d"}
    assert fused[0][2].keys() == {"bm25", "dense"}


def test_bm25_finds_the_cuban_rule():
    hits = BM25Index(CHUNKS).search("cuban origin cigars", k=1)
    assert hits[0].citation == "31cfr515:515.204"


def test_collection_name():
    assert collection_name("paragraph") == "customs__paragraph__bge-small-en-v1-5"


def test_dense_store_roundtrip_and_stale_check():
    store = DenseStore(QdrantClient(location=":memory:"), "customs__test")
    store.recreate(3)
    vecs = [[[1.0, 0.0, 0.0]], [[0.0, 1.0, 0.0]], [[0.0, 0.0, 1.0]]]
    store.upsert(CHUNKS, vecs, "bge-small-en-v1.5", "hash1")
    assert store.check("bge-small-en-v1.5", "hash1") == 3
    with pytest.raises(StaleIndex):
        store.check("bge-small-en-v1.5", "other")
    assert store.search([0.0, 0.9, 0.1], k=1)[0].chunk_id == "c2"


def test_hybrid_without_reranker():
    store = DenseStore(QdrantClient(location=":memory:"), "customs__test")
    store.recreate(3)
    store.upsert(CHUNKS, [[[1.0, 0.0, 0.0]], [[0.0, 1.0, 0.0]], [[0.0, 0.0, 1.0]]], "m", "h")
    hr = HybridRetriever(BM25Index(CHUNKS), store, lambda q: [0.0, 0.0, 1.0])
    hits = hr.search("Cuban origin", k=2)
    assert hits[0].chunk_id == "c3"
    assert set(hits[0].ranks) == {"bm25", "dense"}


def test_listwise_parse():
    assert ListwiseReranker.parse("3, 1", n_docs=4, top_n=3) == [2, 0, 1]
    assert ListwiseReranker.parse("[9], [2]", n_docs=3, top_n=2) == [1, 0]
    assert ListwiseReranker.parse("none fit", n_docs=3, top_n=2) is None


def test_listwise_rerank_reports_its_call(settings):
    events = []

    def handler(request):
        return httpx.Response(200, json=chat_response("2, 1", prompt_tokens=300))

    chat = ChatClient(settings, client=mock_openai(handler))
    rr = ListwiseReranker(settings, chat=chat, observer=events.append)
    assert [i for i, _ in rr.rerank("q", ["a", "b", "c"], 2)] == [1, 0]
    assert events[0]["event"] == "rerank" and events[0]["tokens"] == 310


def test_embedder_windows_and_batches(settings):
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        data = [
            {"object": "embedding", "index": i, "embedding": [0.1, 0.2, 0.3]}
            for i in range(len(body["input"]))
        ]
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": body["model"],
                "data": data,
                "usage": {"prompt_tokens": 5, "total_tokens": 5},
            },
        )

    try:
        emb = Embedder(settings, client=mock_openai(handler))
    except Exception as err:  # noqa: BLE001 - offline machine without a cached tokenizer
        pytest.skip(f"tokenizer unavailable: {err}")
    long_text = "duty " * 1200
    assert len(emb.windows(long_text)) > 1
    vectors = emb.embed_chunks(["short"] * 20 + [long_text])
    assert len(vectors) == 21 and len(vectors[-1]) > 1
    assert all(len(b["input"]) <= 16 for b in seen)
    assert seen[0]["model"] == "bge-small-en-v1.5"
    emb.embed_query("can I bring wine")
    assert seen[-1]["input"][0].startswith("Represent this sentence")
