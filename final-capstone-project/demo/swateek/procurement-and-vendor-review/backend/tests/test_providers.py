"""PROVIDER=siliconflow|upgrad: profiles, TLS, the one-request gate, windows, per-model indexes."""

import json
import ssl
import threading
import time

import httpx
import pytest
from pydantic import ValidationError
from qdrant_client import QdrantClient

from copilot.config import PROJECT_ROOT, Settings
from copilot.llm.providers import (
    ProviderNotConfigured,
    get_embedding,
    get_provider,
    get_reranker,
    make_http_client,
    validate,
)
from copilot.llm.retry import GatedTransport, RateGate
from copilot.retrieval.dense import DenseStore, collection_name

KEYS = {"siliconflow_api_key": "sk-sf-secret", "upgrad_embed_api_key": "emb-secret"}


def upgrad(**kw) -> Settings:
    base = {"upgrad_chat_api_key": "grp-secret", **KEYS}
    return Settings(_env_file=None, domain="test", provider="upgrad", **{**base, **kw})


def test_course_is_renamed_to_upgrad():
    with pytest.raises(ValidationError, match="upgrad"):
        Settings(_env_file=None, domain="test", llm_provider="course")


def test_old_env_name_still_selects_the_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "upgrad")
    assert Settings(_env_file=None, domain="test").provider == "upgrad"
    monkeypatch.setenv("PROVIDER", "siliconflow")  # the new name wins
    assert Settings(_env_file=None, domain="test").provider == "siliconflow"


def test_upgrad_chat_profile():
    p = get_provider(upgrad())
    assert p.base_url == "https://103.42.50.41:1033/v1"
    assert p.model == "Qwen/Qwen3-8B"
    assert p.max_concurrency == 1  # one active request per group key
    assert p.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
    assert p.ca_cert == PROJECT_ROOT / "certs" / "vm05-ca.crt"
    assert "grp-secret" not in repr(p)


def test_upgrad_embedding_and_reranker_profiles():
    s = upgrad()
    e = get_embedding(s)
    assert (e.model, e.batch_size, e.max_tokens, e.query_style) == (
        "bge-small-en-v1.5",
        16,
        512,
        "bge",
    )
    assert e.ca_cert == PROJECT_ROOT / "certs" / "vm02-ca.crt"
    r = get_reranker(s)  # Track B requires a reranker; the course has none, so the chat model
    assert (r.kind, r.model, r.base_url) == ("chat_listwise", "Qwen/Qwen3-8B", p_chat_url())
    assert r.max_concurrency == 1 and "grp-secret" not in repr(r)
    assert get_reranker(upgrad(upgrad_reranker="none")) is None


def p_chat_url() -> str:
    return "https://103.42.50.41:1033/v1"


def test_siliconflow_profile_is_unchanged():
    s = Settings(_env_file=None, domain="test", **KEYS)
    assert get_provider(s).extra_body == {"enable_thinking": False}
    assert get_provider(s).ca_cert is None
    assert get_embedding(s).model == "Qwen/Qwen3-Embedding-0.6B"
    assert get_embedding(s).max_tokens is None
    assert get_reranker(s).model == "Qwen/Qwen3-Reranker-8B"


@pytest.mark.parametrize(
    ("override", "var"),
    [
        ({"upgrad_chat_api_key": None}, "UPGRAD_CHAT_API_KEY"),
        ({"upgrad_embed_api_key": ""}, "UPGRAD_EMBED_API_KEY"),
        ({"upgrad_chat_ca_cert": "certs/missing.crt"}, "UPGRAD_CHAT_CA_CERT"),
    ],
)
def test_startup_check_names_the_missing_setting(override, var):
    with pytest.raises(ProviderNotConfigured, match=var):
        validate(upgrad(**override))


def test_upgrad_never_needs_siliconflow():
    validate(upgrad(siliconflow_api_key=None))
    validate(upgrad(siliconflow_api_key=None, upgrad_reranker="none"))


def test_upgrad_reranker_rejects_siliconflow():
    with pytest.raises(ValidationError):
        upgrad(upgrad_reranker="siliconflow")


class _FakeChat:
    def __init__(self, reply: str) -> None:
        self.reply, self.seen = reply, []
        self.chat = self
        self.completions = self

    def create(self, **kw):
        self.seen.append(kw)
        msg = type("M", (), {"content": self.reply})()
        usage = type("U", (), {"total_tokens": 7})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()], "usage": usage})()


def _chat_reranker(reply: str):
    from copilot.retrieval.rerank import ChatReranker, make_reranker

    s = upgrad()
    rr = make_reranker(s, get_reranker(s), instruction="Find the rule")
    assert isinstance(rr, ChatReranker)
    rr.client = _FakeChat(reply)
    return rr


def test_chat_reranker_follows_the_models_order():
    rr = _chat_reranker("<think></think>3, 1, 3, 99, 2")
    docs = [f"passage {i}" for i in range(6)]
    assert [i for i, _ in rr.rerank("q", docs, 4)] == [2, 0, 1, 3]  # dupes/out-of-range dropped
    sent = rr.client.seen[0]
    assert sent["max_tokens"] <= 64 and sent["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False}
    }
    assert rr.tokens_used == 7 and rr.fallbacks == 0


def test_chat_reranker_keeps_fused_order_on_a_useless_reply():
    rr = _chat_reranker("I cannot rank these.")
    assert [i for i, _ in rr.rerank("q", ["a", "b", "c"], 2)] == [0, 1]
    assert rr.fallbacks == 1


def test_chat_reranker_prompt_fits_the_window():
    from copilot.llm.budget import count_message_tokens

    rr = _chat_reranker("1")
    long = " ".join(f"Clause {i} sets the limit for purchases." for i in range(400))
    msgs = rr.messages("What is the limit?", [long] * 20, 5)
    assert count_message_tokens(rr.tok, msgs) <= rr.settings.context_window_tokens - 40


def test_tls_is_verified_against_the_course_ca():
    client = make_http_client(get_provider(upgrad()), 5)
    ctx = client._transport._inner._pool._ssl_context
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    roots = ctx.get_ca_certs()
    assert len(roots) == 1 and "Caddy Local Authority" in str(roots[0]["subject"])


def test_gate_allows_one_request_at_a_time_and_frees_on_errors():
    active, peak = 0, 0
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        if request.url.path == "/fail":
            raise httpx.ConnectError("down")
        # a streamed body, like a real transport's: the gate frees when it is closed
        return httpx.Response(200, stream=httpx.ByteStream(b'{"ok": true}'))

    gate = RateGate(1, 600)
    client = httpx.Client(transport=GatedTransport(httpx.MockTransport(handler), gate))

    def call(path: str) -> None:
        try:
            client.get(f"http://test{path}")
        except httpx.ConnectError:
            pass

    threads = [threading.Thread(target=call, args=(p,), daemon=True) for p in ["/ok", "/fail"] * 3]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert peak == 1
    assert gate._sem.acquire(timeout=0.1)


def test_long_chunks_are_embedded_as_windows_within_the_limit():
    from copilot.retrieval.embed import Embedder

    e = Embedder(upgrad())
    long = " ".join(f"clause {i} of the procurement rule" for i in range(400))
    wins = e.windows(long)
    assert len(wins) > 1
    sizes = [len(e.tok.encode(w, add_special_tokens=False).ids) for w in wins]
    assert max(sizes) <= e.window <= 512 - 2
    assert long.startswith(wins[0]) and long.endswith(wins[-1])
    assert e.windows("short text") == ["short text"]

    calls = []
    e._embed = lambda texts: calls.append(len(texts)) or [[0.0] for _ in texts]
    out = e.embed_chunks([long, "short text"])
    assert [len(v) for v in out] == [len(wins), 1]
    assert max(calls) <= 16


def test_siliconflow_keeps_its_collection_and_upgrad_gets_its_own():
    sf = get_embedding(Settings(_env_file=None, domain="test", **KEYS))
    up = get_embedding(upgrad())
    assert collection_name("d", "by_rule", sf.collection_suffix) == "d__by_rule"  # unchanged
    assert collection_name("d", "by_rule", up.collection_suffix) == "d__by_rule__bge-small-en-v1-5"


def test_dense_search_keeps_one_hit_per_chunk():
    store = DenseStore(QdrantClient(":memory:"), "t")
    store.recreate(2)
    chunks = [
        {"chunk_id": "c1", "citation": "x:1", "doc_id": "x"},
        {"chunk_id": "c2", "citation": "x:2", "doc_id": "x"},
    ]
    store.upsert(chunks, [[[1.0, 0.0], [0.9, 0.1]], [[0.0, 1.0]]], "m", "h")
    assert store.client.count("t").count == 3
    hits = store.search([1.0, 0.0], k=2)
    assert [h.chunk_id for h in hits] == ["c1", "c2"]


def test_results_go_to_a_directory_per_provider():
    assert upgrad().results_dir == PROJECT_ROOT / "docs" / "results" / "upgrad"
    sf = Settings(_env_file=None, domain="test")
    assert sf.results_dir == PROJECT_ROOT / "docs" / "results" / "siliconflow"


def test_judge_refuses_runs_from_the_course_endpoint(tmp_path, monkeypatch):
    from eval import judge

    run = tmp_path / "e2e-v3-upgrad-run1.json"
    run.write_text(json.dumps({"meta": {"provider": "upgrad"}, "rows": []}))
    monkeypatch.setattr(judge, "RESULTS", tmp_path)
    monkeypatch.setattr("sys.argv", ["judge", run.name])
    with pytest.raises(SystemExit, match="only SiliconFlow runs"):
        judge.main()
    monkeypatch.setattr("sys.argv", ["judge", "not-here.json"])
    with pytest.raises(SystemExit, match="not judged"):
        judge.main()


def test_chat_reranker_call_is_recorded_in_the_run():
    from copilot.agent.context import RunContext, activate, deactivate

    rr = _chat_reranker("2, 1")
    ctx = RunContext(step_limit=10, tool_limit=10, token_limit=40000)
    token = activate(ctx)
    try:
        rr.rerank("q", ["a", "b"], 2)
    finally:
        deactivate(token)
    (ev,) = [e for e in ctx.events if e["type"] == "rerank"]
    assert ev["tokens"] == 7 and ev["fallback"] is False
    assert ctx.tokens == 7 and ctx.steps == 0  # counts toward the token cap, not the step cap


def test_long_query_is_cut_to_fit_the_embedding_endpoint():
    from copilot.retrieval.embed import Embedder

    e = Embedder(upgrad())
    sent = []
    e._embed = lambda texts: sent.extend(texts) or [[0.0]]
    e.embed_query("why " * 900)
    assert sent[0].startswith(e.query_prefix)
    assert len(e.tok.encode(sent[0], add_special_tokens=False).ids) <= e.window


def test_upgrad_costs_no_money():
    from eval.e2e import PRICES

    assert set(PRICES["upgrad"].values()) == {0.0}
