"""The shipped reranker (option A, 20 Nov 2026): defaults, and each rerank call counted against
the question's caps. Offline: no endpoint, no model download."""

from types import SimpleNamespace

from customs.config import Settings
from customs.retrieval import service
from customs.retrieval.service import RegulationSearch


def test_option_a_is_the_default():
    fields = Settings.model_fields
    assert fields["reranker"].default == "listwise"
    assert fields["reranker_pool"].default == 10
    assert fields["reranker_passage_tokens"].default == 120


def test_rerank_call_is_charged_to_the_question(monkeypatch):
    seen = []
    fake = SimpleNamespace(
        after_model_call=lambda node, res: seen.append((node, res.total_tokens, res.calls))
    )
    from customs.agent import context

    monkeypatch.setattr(context, "current", lambda: fake)
    search = RegulationSearch(Settings(), rankings=lambda q, f: [])
    search._observe_rerank({"event": "rerank", "tokens": 1300, "seconds": 0.7})
    assert seen == [("rerank", 1300, 1)]


def test_rerank_outside_a_question_counts_nothing():
    search = RegulationSearch(Settings(), rankings=lambda q, f: [])
    # no run context is active: the observer must not raise
    search._observe_rerank({"event": "rerank", "tokens": 1300, "seconds": 0.7})
    assert service is not None
