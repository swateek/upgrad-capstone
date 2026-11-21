"""The API offline: the real FastAPI app over a scripted agent (dev facts), in-process store,
temp sessions. No upgrad call."""

from __future__ import annotations

import json
import re
import threading

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from test_agent import DV01, REVIEW_OK, WINE_PLAN, FakeCorpus, Script, writer_ok

from customs.agent.graph import CustomsAgent
from customs.api import app as api
from customs.api.service import AgentService, ProgressTracer, correction_message
from customs.api.sessions import Sessions
from customs.api.store import MemoryKV
from customs.llm.chat import ChatClient
from customs.retrieval.service import RegulationSearch
from customs.tools.tables import load_tables

from conftest import mock_openai  # isort: skip


def events_of(resp) -> list[dict]:
    out = []
    for block in resp.text.strip().split("\n\n"):
        data = [ln[6:] for ln in block.splitlines() if ln.startswith("data: ")]
        if data:
            out.append(json.loads(data[0]))
    return out


@pytest.fixture
def make_client(settings, tmp_path):
    def make(script: Script, **overrides):
        s = settings.model_copy(update={"data_dir": tmp_path, **overrides})
        t = load_tables()
        tracer = ProgressTracer(s)
        agent = CustomsAgent(
            s, chat=ChatClient(s, client=mock_openai(script.handler), tracer=tracer),
            search=RegulationSearch(s, rankings=lambda qs, fs: [[] for _ in qs],
                                    corpus=FakeCorpus(t), tables=t),
            checkpointer=InMemorySaver(), tracer=tracer, tables=t,
        )  # fmt: skip
        svc = AgentService(s, agent=agent, kv=MemoryKV(),
                           sessions=Sessions(tmp_path / "s.sqlite", s.session_ttl_s,
                                             agent.checkpointer.delete_thread))  # fmt: skip
        api.app.state.service = svc
        return TestClient(api.app), svc

    yield make
    api.app.state.service = None


def full_script(n: int = 1) -> Script:
    return Script(intake=[DV01] * n, planner=[WINE_PLAN] * n, writer=[writer_ok(DV01)] * n,
                  review=[REVIEW_OK] * n)  # fmt: skip


def test_health_is_offline(make_client):
    client, _ = make_client(Script())
    h = client.get("/health").json()
    assert h["status"] == "ok" and re.fullmatch(r"v\d+|unfrozen", h["agent"])


def test_chat_streams_progress_then_card_and_thread_is_readable(make_client):
    client, _ = make_client(full_script())
    ev = events_of(client.post("/chat", json={"message": "Back from Vienna, what do I owe?"}))
    kinds = [e["event"] for e in ev]
    assert kinds[0] == "started" and kinds[-1] == "card"
    nodes = [e["node"] for e in ev if e["event"] == "node"]
    assert nodes[:3] == ["guard", "intake", "prepare"] and "verify" in nodes
    card = ev[-1]["card"]
    assert card["owe_usd"] == "1.45"
    t = client.get(f"/threads/{ev[-1]['thread_id']}").json()
    assert t["facts"]["profile"]["age"] == 49 and t["card"]["outcome"] == "answered"
    assert client.get("/threads/unknown-thread-123").status_code == 404


def test_answer_cache_hit_seeds_the_thread(make_client):
    sc = full_script(1)
    client, _ = make_client(sc)
    q = {"message": "Back from Vienna, what do I owe?"}
    first = events_of(client.post("/chat", json=q))[-1]
    seen = len(sc.seen)
    second = events_of(client.post("/chat", json=q))[-1]  # a new thread, same question
    assert len(sc.seen) == seen  # no model call
    assert second["card"]["meta"]["cached"] is True and second["thread_id"] != first["thread_id"]
    seeded = client.get(f"/threads/{second['thread_id']}").json()
    assert seeded["facts"] == client.get(f"/threads/{first['thread_id']}").json()["facts"]


def test_cache_off_runs_live(make_client):
    client, _ = make_client(full_script(2), answer_cache_enabled=False)
    q = {"message": "Back from Vienna, what do I owe?"}
    events_of(client.post("/chat", json=q))
    card = events_of(client.post("/chat", json=q))[-1]["card"]
    assert not card["meta"].get("cached")


def test_rate_limit_per_conversation(make_client):
    client, _ = make_client(Script(), rate_limit_chat_per_min=1)
    tid = "thread-rate-1"
    assert (
        client.post(
            "/chat", json={"message": "hide my cigars please", "thread_id": tid}
        ).status_code
        == 200
    )
    r = client.post("/chat", json={"message": "hide them", "thread_id": tid})
    assert r.status_code == 429 and "conversation" in r.json()["detail"]


def test_facts_edit_is_asked_as_a_correction(make_client):
    sc = full_script(2)
    client, _ = make_client(sc)
    tid = events_of(client.post("/chat", json={"message": "Vienna wine"}))[-1]["thread_id"]
    r = client.post(
        f"/threads/{tid}/facts", json={"profile": {"age": 20}, "lines": {"1": {"value_usd": 50}}}
    )
    ev = events_of(r)
    assert ev[-1]["event"] == "card"
    assert (
        client.post(f"/threads/{tid}/facts", json={"profile": {"us_resident": False}}).status_code
        == 422
    )


def test_correction_message_wording():
    msg = correction_message({"age": 20, "exemption_used_last_30_days": True},
                             {1: {"value_usd": 50, "quantity": 4}}, [{"item": "wine"}])  # fmt: skip
    assert msg == ("Correction to my facts: I am 20 years old. I have used my duty-free exemption "
                   "in the last 30 days. Item 1 (wine): there are 4 of them; I paid $50.00 in total.")  # fmt: skip


def test_second_question_waits_with_a_queued_event(make_client):
    _client, svc = make_client(Script())
    got: list[dict] = []
    svc.busy.acquire()
    try:
        t = threading.Thread(
            target=lambda: got.extend(svc.ask("thread-queue-1", "hide my cigars", "c")), daemon=True
        )
        t.start()
        t.join(0.5)
        assert t.is_alive()  # waiting behind the busy key; the client has been told so
    finally:
        svc.busy.release()
    t.join(5)
    assert [e["event"] for e in got][:2] == ["queued", "started"] and got[-1]["event"] == "card"


def test_sessions_expire_and_are_purged(tmp_path):
    now = [1000.0]
    deleted: list[str] = []
    s = Sessions(
        tmp_path / "s.sqlite", ttl_s=60, delete_thread=deleted.append, clock=lambda: now[0]
    )
    s.touch("a")
    assert s.known("a")
    now[0] += 61
    assert not s.known("a")
    assert s.purge(force=True) == ["a"] and deleted == ["a"]


def test_memory_kv_ttl_and_windows():
    now = [0.0]
    kv = MemoryKV(clock=lambda: now[0])
    kv.set_json("k", {"a": 1}, ttl_s=10)
    assert kv.get_json("k") == {"a": 1}
    now[0] = 11
    assert kv.get_json("k") is None
    assert [kv.hit("r", 60) for _ in range(3)] == [1, 2, 3]
    now[0] = 61
    assert kv.hit("r", 60) == 1


def test_pii_questions_are_never_cached_and_cache_ttl_is_capped(make_client):
    sc = full_script(2)
    client, svc = make_client(sc)
    q = {"message": "Back from Vienna, what do I owe? Email me at pat@example.com"}
    events_of(client.post("/chat", json=q))
    events_of(client.post("/chat", json=q))  # same question again: answered live, not from cache
    assert sc.seen.count("intake") == 2
    assert svc.cache_ttl_s <= svc.settings.session_ttl_s


def test_no_docs_or_schema_exposed(make_client):
    client, _ = make_client(Script())
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_ablation_modes_are_not_served(settings, tmp_path):
    for mode in ("single_rag", "tool_calling"):
        with pytest.raises(ValueError, match="serves"):
            AgentService(settings.model_copy(update={"agent_mode": mode, "data_dir": tmp_path}))
