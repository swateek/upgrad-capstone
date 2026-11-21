"""search_regulations and the saved index, on a tiny synthetic corpus (no network, no model download)."""

from __future__ import annotations

import numpy as np
import pytest

from src.retrieval.index import (
    IndexMismatch,
    build_index,
    load_index,
    load_or_build,
)
from src.retrieval.retriever import Retriever
from src.tools.common import ToolError
from src.tools.search_regulations import Args, RegulationSearch
from tests.test_retrieval import CHUNKS, FakeReranker, fake_embed

# a second chunk of 148.51, about tobacco, so "by id" has to choose within the section
CORPUS = [
    *CHUNKS,
    {
        "chunk_id": "a#02",
        "citation_id": "19cfr148.51",
        "authority": "primary_regulation",
        "text": "Special exemption: cigarettes and cigars over the limit make the whole exemption unavailable",
    },
    {
        "chunk_id": "e#01",
        "citation_id": "notes-curated",
        "authority": "curated_secondary",
        "text": "Our notes: special exemption 150 milliliters alcoholic beverages cigarettes cigars",
    },
]


class CountingEmbed:
    def __init__(self) -> None:
        self.calls = 0
        self.texts = 0

    def __call__(self, texts):
        self.calls += 1
        self.texts += len(texts)
        return fake_embed(texts)


def search(**kw) -> RegulationSearch:
    return RegulationSearch(CORPUS, fake_embed, **kw)


def test_by_id_takes_the_rule_the_tools_applied() -> None:
    out = search()(Args(query="flat rate duty", citation_ids=["19cfr148.51"], k=1))
    assert [c.citation_id for c in out.clauses] == ["19cfr148.51"]
    assert out.clauses[0].found_by == "citation_id"
    assert out.retrieved_ids == ["19cfr148.51"]


def test_by_id_picks_the_chunk_of_the_section_that_matches_the_query() -> None:
    s = search()
    alcohol = s(Args(query="150 milliliters alcoholic beverages", citation_ids=["19cfr148.51"], k=1))
    tobacco = s(Args(query="cigarettes over the limit whole exemption unavailable", citation_ids=["19cfr148.51"], k=1))
    assert alcohol.clauses[0].chunk_id == "a#01"
    assert tobacco.clauses[0].chunk_id == "a#02"


def test_ids_are_normalised_and_unknown_ids_reported() -> None:
    out = search()(Args(query="duty", citation_ids=[" 19CFR148.51 ", "19cfr999.1"], k=2))
    assert out.clauses[0].citation_id == "19cfr148.51"
    assert out.not_found == ["19cfr999.1"]


def test_hard_negatives_and_curated_notes_are_never_returned() -> None:
    out = search()(
        Args(
            query="crewmembers 50 cigarettes 10 cigars 150 milliliters notes",
            citation_ids=["19cfr148.64", "notes-curated"],
        )
    )
    assert out.not_found == ["19cfr148.64", "notes-curated"]
    authorities = {c.authority for c in out.clauses}
    assert not authorities & {"hard_negative", "curated_secondary"}
    assert "19cfr148.64" not in out.retrieved_ids


def test_search_fills_the_rest_one_chunk_per_citation() -> None:
    out = search()(
        Args(
            query="special exemption 150 milliliters cigarettes cigars proof gallon",
            citation_ids=["htsus9816.00.20"],
            k=4,
        )
    )
    ids = [c.citation_id for c in out.clauses]
    assert ids[0] == "htsus9816.00.20" and out.clauses[0].found_by == "citation_id"
    assert len(ids) == len(set(ids)) <= 4
    assert all(c.found_by == "search" and c.rank for c in out.clauses[1:])
    assert out.retrieved_ids == ids


def test_ids_fill_the_budget_so_no_search_is_run() -> None:
    class NoRank(Retriever):
        def rank(self, query):  # pragma: no cover - must not be called
            raise AssertionError("search should not run when ids fill k")

    s = search()
    s.retriever.__class__ = NoRank
    out = s(Args(query="x", citation_ids=["19cfr148.51", "htsus9816.00.20"], k=2))
    assert [c.found_by for c in out.clauses] == ["citation_id", "citation_id"]


def test_reranker_is_used_and_named() -> None:
    s = search(reranker=FakeReranker(), reranker_name="fake-reranker")
    out = s(Args(query="duty rates spirits wine", k=1))
    assert out.method == "hybrid+fake-reranker"
    assert out.clauses[0].citation_id == "ttb-tax-rates"  # the fake reranker prefers "proof"
    assert search().method == "hybrid"


def test_nothing_found_escalates() -> None:
    tiny = [c for c in CORPUS if c["authority"] == "hard_negative"]
    with pytest.raises(ToolError) as e:
        RegulationSearch(tiny, fake_embed)(Args(query="crewmembers"))
    assert e.value.code == "escalate"


def test_k_is_capped_at_five() -> None:
    with pytest.raises(ValueError):
        Args(query="x", k=6)


# ------------------------------------------------------------------ saved index


def test_index_round_trip_and_reuse(tmp_path) -> None:
    emb = CountingEmbed()
    m = build_index(CORPUS, emb, "fake-model", tmp_path)
    assert np.allclose(np.linalg.norm(m, axis=1), 1, atol=1e-5)
    again = load_or_build(CORPUS, emb, "fake-model", tmp_path, log=lambda _: None)
    assert emb.calls == 1  # loaded from disk, not re-embedded
    assert np.array_equal(m, again)


def test_index_is_rebuilt_when_chunks_or_model_change(tmp_path) -> None:
    build_index(CORPUS, fake_embed, "fake-model", tmp_path)
    changed = [dict(c) for c in CORPUS]
    changed[0]["text"] += " (amended)"
    with pytest.raises(IndexMismatch):
        load_index(changed, "fake-model", tmp_path)
    with pytest.raises(IndexMismatch):
        load_index(CORPUS, "other-model", tmp_path)
    emb = CountingEmbed()
    load_or_build(changed, emb, "fake-model", tmp_path, log=lambda _: None)
    assert emb.texts == len(changed)
    load_index(changed, "fake-model", tmp_path)  # now matches


def test_saved_matrix_gives_the_same_results_as_embedding(tmp_path) -> None:
    m = build_index(CORPUS, fake_embed, "fake-model", tmp_path)
    q = Args(query="spirits proof gallon excise")
    a = RegulationSearch(CORPUS, fake_embed, matrix=m)(q)
    b = RegulationSearch(CORPUS, fake_embed)(q)
    assert [c.chunk_id for c in a.clauses] == [c.chunk_id for c in b.clauses]


def test_set_matrix_rejects_wrong_row_count() -> None:
    r = Retriever(CORPUS, method="hybrid", embed=fake_embed)
    with pytest.raises(ValueError):
        r.set_matrix(np.zeros((2, 64), dtype=np.float32))
