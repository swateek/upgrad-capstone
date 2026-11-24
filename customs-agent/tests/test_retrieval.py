"""Retriever: BM25, dense, RRF hybrid, reranker and metadata filter on a tiny synthetic corpus."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from eval.retrieval_experiment import evaluate, first_hit
from src.retrieval.retriever import Retriever, rrf, tokenize

CHUNKS = [
    {
        "chunk_id": "a#01",
        "citation_id": "19cfr148.51",
        "authority": "primary_regulation",
        "text": "Special exemption $200: 50 cigarettes, 10 cigars, 150 milliliters of alcoholic beverages for returning residents",
    },
    {
        "chunk_id": "b#01",
        "citation_id": "19cfr148.64",
        "authority": "hard_negative",
        "text": "Crewmembers exemption: 50 cigarettes, 10 cigars, 150 milliliters of alcoholic beverages",
    },
    {
        "chunk_id": "c#01",
        "citation_id": "htsus9816.00.20",
        "authority": "primary_regulation",
        "text": "HTSUS 9816.00.20 flat rate 3 percent on the next $1,000 of fair retail value",
    },
    {
        "chunk_id": "d#01",
        "citation_id": "ttb-tax-rates",
        "authority": "tax_rates",
        "text": "Distilled spirits $13.50 per proof gallon; still wine not over 16% $1.07 per wine gallon",
    },
    # filler, so BM25 term weights behave as in a real corpus
    *[
        {
            "chunk_id": f"f{i}#01",
            "citation_id": f"filler-{i}",
            "authority": "agency_guidance",
            "text": t,
        }
        for i, t in enumerate(
            [
                "pets entering the country need vaccination records",
                "currency over ten thousand dollars must be reported",
                "fruits and vegetables may carry plant pests",
                "firearms need a permit to be taken abroad",
            ]
        )
    ],
]


def fake_embed(texts):
    """Bag-of-words hashed into 64 dims: similar words, similar vectors (no network)."""
    out = []
    for t in texts:
        v = np.zeros(64)
        for w in tokenize(t):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1
        out.append(v.tolist())
    return out


class FakeReranker:
    def predict(self, pairs):  # prefers chunks mentioning "proof"
        return [1.0 if "proof" in text else 0.0 for _, text in pairs]


def test_tokenizer_keeps_section_numbers_whole() -> None:
    assert tokenize("See 19 CFR 148.33 and HTSUS 9816.00.20.") == [
        "see",
        "19",
        "cfr",
        "148.33",
        "and",
        "htsus",
        "9816.00.20",
    ]


def test_rrf_rewards_agreement() -> None:
    assert rrf([[1, 2, 3], [2, 1, 3]])[:2] in ([1, 2], [2, 1])
    assert rrf([[5, 6], [6, 7]])[0] == 6  # in both lists


@pytest.mark.parametrize("method", ["bm25", "dense", "hybrid"])
def test_methods_find_the_flat_rate(method) -> None:
    r = Retriever(CHUNKS, method=method, filter="none", embed=fake_embed)
    assert (
        r.search("3 percent flat rate on the next $1,000", k=1)[0]["citation_id"]
        == "htsus9816.00.20"
    )


def test_filter_drops_hard_negatives_before_ranking() -> None:
    q = "50 cigarettes 10 cigars 150 milliliters crewmembers"
    unfiltered = Retriever(CHUNKS, method="bm25", filter="none").search(q, k=4)
    filtered = Retriever(CHUNKS, method="bm25", filter="no_hard_negatives").search(
        q, k=4
    )
    assert unfiltered[0]["citation_id"] == "19cfr148.64"
    assert (
        all(r["authority"] != "hard_negative" for r in filtered)
        and filtered[0]["citation_id"] == "19cfr148.51"
    )


def test_reranker_reorders_the_hybrid_pool() -> None:
    r = Retriever(
        CHUNKS,
        method="hybrid_rerank",
        filter="none",
        embed=fake_embed,
        reranker=FakeReranker(),
    )
    assert r.search("tax rate", k=1)[0]["citation_id"] == "ttb-tax-rates"


def test_misconfiguration_is_refused() -> None:
    with pytest.raises(ValueError):
        Retriever(CHUNKS, method="dense")
    with pytest.raises(ValueError):
        Retriever(CHUNKS, method="hybrid_rerank", embed=fake_embed)


def test_recall_and_mrr() -> None:
    r = Retriever(CHUNKS, method="bm25", filter="no_hard_negatives")
    qs = [
        {"id": "Q1", "query": "flat rate 3 percent", "gold": ["htsus9816.00.20"]},
        {"id": "Q2", "query": "proof gallon spirits", "gold": ["nonexistent"]},
    ]
    row, per = evaluate(r, qs)
    assert (
        row["recall@1"] == 0.5
        and row["mrr@10"] == 0.5
        and per[1]["first_hit_rank"] is None
    )
    assert first_hit([{"rank": 2, "citation_id": "x"}], {"x"}) == 2
