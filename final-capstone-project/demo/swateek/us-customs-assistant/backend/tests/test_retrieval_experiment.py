"""The code-built search query and the retrieval experiment runner, offline: tiny corpus, fake
embedder, fake rerankers, temp outputs. No upgrad call, no model download."""

import json

import pytest

from customs.config import Settings
from customs.ingest import index as ix
from customs.retrieval import rerank as rr
from customs.retrieval.query import build_query, rule_key, scope, search_terms
from customs.tools.tables import load_tables
from eval import retrieval as rx


def test_rule_key_and_search_terms():
    t = load_tables()
    assert rule_key("R9 which_exemption") == "R9"
    assert rule_key("CA arrival-state flag") == "CA"
    assert search_terms(t, "R7") == "flat rate duty"
    assert search_terms(t, "CA").startswith("California")
    q = build_query("  What do I owe? ", t, ["R7", "R8", "R7"])
    assert q == "What do I owe?\nflat rate duty; excise general rates"
    assert build_query("Hi", t) == "Hi"


def test_scope_follows_the_rules_cites():
    t = load_tables()
    topics = {"cfr19_p148": "exemptions", "ttb_tax_rates": "rates", "usc26_5001": "rates",
              "cfr31_p515": "sanctions", "state_ca": "state", "other": "other_goods"}  # fmt: skip
    assert scope(t, ["R8"], topics) == {"ttb_tax_rates", "usc26_5001"}
    assert scope(t, ["CA"], topics) == {"state_ca"}
    assert "cfr31_p515" in scope(t, ["R4"], topics)
    assert scope(t, [], topics) == set()


def test_memo_scores_each_pair_once():
    class Inner:
        model = "fake"
        calls = 0

        def rerank(self, query, docs, top_n):
            Inner.calls += len(docs)
            return sorted(((i, float(len(d))) for i, d in enumerate(docs)), key=lambda x: -x[1])

    m = rx.Memo(Inner())
    assert [i for i, _ in m.rerank("q", ["a", "ccc", "bb"], 2)] == [1, 2]
    assert [i for i, _ in m.rerank("q", ["bb", "a", "dddd"], 3)] == [2, 0, 1]
    assert Inner.calls == 4  # "a", "bb" scored once


def test_metrics():
    items = [
        rx.Item(f"R{i}#0", f"R{i}", "dev", "c", "R9", frozenset(), "q", "qr", frozenset())
        for i in range(4)
    ]
    per = {"R0#0": {"hit": 1, "hit_tok": 90, "tok5": 100, "neg5": False},
           "R1#0": {"hit": 4, "hit_tok": 1600, "tok5": 300, "neg5": True},
           "R2#0": {"hit": None, "hit_tok": None, "tok5": 200, "neg5": False},
           "R3#0": {"hit": 10, "hit_tok": 1400, "tok5": 200, "neg5": False}}  # fmt: skip
    m = rx.metrics(per, items)
    assert (m["recall@1"], m["recall@3"], m["recall@5"], m["recall@10"]) == (0.25, 0.25, 0.5, 0.75)
    assert m["mrr@10"] == pytest.approx((1 + 0.25 + 0.1) / 4)
    assert m["recall@budget"] == 0.5  # token-matched: R1 is past 1,500 tokens, R3 is not
    assert m["full@5"] == 0.5 and m["tok5"] == 200 and m["neg5"] == 0.25


def test_variant_grid():
    vs = rx.variants()
    assert len(vs) == 63 and len({v.name for v in vs}) == 63
    assert not any(v.query == "q" and v.filter == "topic" for v in vs)
    assert all(v.prefix == "-" for v in vs if v.retriever == "bm25")
    assert rx.Variant.parse(vs[5].name) == vs[5]


# --- end to end on a tiny corpus ---------------------------------------------------------------

TEXTS = [
    ("cfr19_p148", "exemptions", "cfr19_p148:148.35(a)", "Returning residents get an $800 exemption."),
    ("cfr19_p148", "exemptions", "cfr19_p148:148.33(d)", "One liter of alcoholic beverages is exempt."),
    ("ttb_tax_rates", "rates", "ttb_tax_rates:spirits", "Distilled spirits excise is $13.50 per proof gallon."),
    ("hts_9816_rows", "rates", "hts_9816_rows:9816.00.20", "A flat rate of duty of 3 percent applies."),
    ("other", "other_goods", "other:food", "Fruit and meat must be declared."),
]  # fmt: skip


class FakeEmbedder:
    requests = 0
    tokens_used = 0

    def embed_documents(self, texts):
        self.requests += -(-len(texts) // 16)
        self.tokens_used += 3 * len(texts)
        return [[float("exempt" in t.lower()), float("rate" in t.lower()), 1.0] for t in texts]


class FakeCE:
    model = "fake-ce"

    def __init__(self, settings):
        pass

    def rerank(self, query, docs, top_n):
        order = sorted(range(len(docs)), key=lambda i: ("duty" not in docs[i], i))
        return [(i, -r) for r, i in enumerate(order[:top_n])]


class FakeListwise:
    model = "fake-listwise"

    def __init__(self):
        self.tokens_used = 0
        self.fallbacks = 0

    def rerank(self, query, docs, top_n):
        self.tokens_used += 50
        return [(i, 1 / (r + 1)) for r, i in enumerate(reversed(range(len(docs))))][:top_n]


@pytest.fixture
def bench(tmp_path, monkeypatch):
    s = Settings(_env_file=None, data_dir=tmp_path / "data", upgrad_embed_api_key="k")
    cdir = s.data_dir / "chunks"
    cdir.mkdir(parents=True)
    for ch in ("paragraph", "section"):
        rows = [{"chunk_id": f"{ch}:{cid}", "chunker": ch, "citation": cid, "clause_ids": [cid],
                 "doc_id": doc, "section_id": "s", "title": "t", "topic": topic,
                 "role": "hard_negative" if doc == "other" else "core", "synthetic": False,
                 "edition": "e", "n_tokens": 10, "text": text}
                for doc, topic, cid, text in TEXTS]  # fmt: skip
        (cdir / f"{ch}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (cdir / "corpus.hash").write_text("h\n")
    log = tmp_path / "quota-log.md"
    log.write_text("| header |\n")
    monkeypatch.setattr(ix, "QUOTA_LOG", log)
    monkeypatch.setattr(rx, "append_quota_log", ix.append_quota_log)
    monkeypatch.setattr(rx, "CHUNKERS", ("paragraph", "section"))
    for name in ("RESULTS", "REPORT", "LISTWISE_RAW"):
        monkeypatch.setattr(rx, name, tmp_path / "out" / getattr(rx, name).name)
    monkeypatch.setattr(rr, "CrossEncoderReranker", FakeCE)
    ix.run(["paragraph", "section"], False, False, "tester", embedder=FakeEmbedder(), settings=s)
    items = [
        rx.Item("A01#0", "A01", "dev", "R9 which_exemption", "R9",
                frozenset({"cfr19_p148:148.35(a)"}), "What exemption do I get?",
                "What exemption do I get?\nwhich exemption", frozenset({"cfr19_p148"})),
        rx.Item("A01#1", "A01", "dev", "R7 flat_rate_duty", "R7",
                frozenset({"hts_9816_rows:9816.00.20"}), "What exemption do I get?",
                "What exemption do I get?\nflat rate duty", frozenset({"hts_9816_rows", "ttb_tax_rates"})),
        rx.Item("B01#0", "B01", "frozen", "R8 excise_general_rates", "R8",
                frozenset({"ttb_tax_rates:spirits"}), "Spirits excise rate?",
                "Spirits excise rate?\nexcise general rates", frozenset({"ttb_tax_rates", "hts_9816_rows"})),
    ]  # fmt: skip
    return s, items, log


def test_end_to_end_local_listwise_report(bench, monkeypatch):
    s, items, log = bench
    # 3 distinct query texts x 2 prefixes... q is shared by A01#0 and A01#1
    assert len(rx.needed_query_texts(items)) == 10
    assert rx.counts(items, s)["embed_requests"] == 1
    assert rx.embed_queries(items, "tester", s, embedder=FakeEmbedder()) == 1
    assert rx.embed_queries(items, "tester", s, embedder=FakeEmbedder()) == 0  # cached
    assert "retrieval experiment: query embeddings" in log.read_text()

    local = rx.run_local(items, s)
    assert len(local) == 42  # 21 variants x 2 chunkers
    rx.save(local)
    v = "paragraph|bm25|-|qr|topic"
    assert local[v]["A01#1"]["hit_tok"] == 10
    assert local[v]["A01#1"]["hit"] == 1  # topic filter keeps the rates sources only
    assert local["paragraph|hybrid+ce|on|qr|off"]["A01#1"]["hit"] == 1  # fake CE puts "duty" first

    base = rx.choose_base(local, items)
    assert base.retriever == "hybrid"
    assert len(rx.listwise_todo(base, items, {"dev"})) == 2
    calls, tokens = rx.run_listwise(base, items, {"dev"}, s, reranker=FakeListwise())
    assert (calls, tokens) == (2, 100)
    assert rx.listwise_todo(base, items, {"dev"}) == []  # resume: nothing left
    lw = rx.listwise_results(items, s)
    assert set(next(iter(lw.values()))) == {"A01#0", "A01#1"}

    text = rx.report(items, s)
    assert "hybrid+listwise" in text and "Listwise: 2 calls" in text
    assert rx.REPORT.exists()
