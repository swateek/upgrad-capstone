"""Tests for src/llm.py against a local mock of the OpenAI-compatible API.

No network, no quota: the mock serves /v1/chat/completions and /v1/embeddings.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from src.endpoints import Endpoint
from src.llm import LLM, BudgetError, LLMError


# --------------------------------------------------------------- mock API
class MockAPI:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.script: deque[tuple[int, dict, dict]] = (
            deque()
        )  # queued (status, body, headers)
        self.in_flight = 0
        self.max_in_flight = 0
        self.delay = 0.0
        self.lock = threading.Lock()
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with api.lock:
                    api.in_flight += 1
                    api.max_in_flight = max(api.max_in_flight, api.in_flight)
                    api.calls.append(
                        {
                            "path": self.path,
                            "body": body,
                            "auth": self.headers.get("Authorization"),
                        }
                    )
                    scripted = api.script.popleft() if api.script else None
                try:
                    time.sleep(api.delay)
                    if scripted:
                        status, payload, headers = scripted
                    elif self.path.endswith("/embeddings"):
                        status, payload, headers = 200, api.embeddings(body), {}
                    else:
                        status, payload, headers = 200, api.chat(body), {}
                    raw = json.dumps(payload).encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.end_headers()
                    self.wfile.write(raw)
                finally:
                    with api.lock:
                        api.in_flight -= 1

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"
        threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.02},
            daemon=True,
        ).start()

    @staticmethod
    def chat(body: dict) -> dict:
        if body.get("tools"):
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "determine_exemption",
                            "arguments": '{"trip_hours": 240}',
                        },
                    }
                ],
            }
            finish = "tool_calls"
        else:
            message = {
                "role": "assistant",
                "content": f"echo:{body['messages'][-1]['content']}",
            }
            finish = "stop"
        return {
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": body["model"],
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
        }

    @staticmethod
    def embeddings(body: dict) -> dict:
        data = [
            {
                "object": "embedding",
                "index": i,
                "embedding": [float(len(t)), float(i)] + [0.0] * 382,
            }
            for i, t in enumerate(body["input"])
        ]
        n = sum(len(t.split()) for t in body["input"])
        return {
            "object": "list",
            "data": data,
            "model": body["model"],
            "usage": {"prompt_tokens": n, "total_tokens": n},
        }

    def error(self, status: int, retry_after: str | None = None) -> None:
        headers = {"Retry-After": retry_after} if retry_after is not None else {}
        self.script.append((status, {"error": {"message": f"mock {status}"}}, headers))

    def chat_calls(self) -> list[dict]:
        return [c for c in self.calls if c["path"].endswith("/chat/completions")]

    def embed_calls(self) -> list[dict]:
        return [c for c in self.calls if c["path"].endswith("/embeddings")]


@pytest.fixture()
def api():
    m = MockAPI()
    yield m
    m.server.shutdown()


@pytest.fixture()
def llm(api, tmp_path: Path) -> LLM:
    chat = Endpoint("chat", api.url, "test-chat-key", model="Qwen/Qwen3-8B")
    embed = Endpoint("embeddings", api.url, "test-embed-key", model="bge-small-en-v1.5")
    return LLM(
        chat_endpoint=chat,
        embed_endpoint=embed,
        run_name="test",
        log_dir=tmp_path,
        base_delay=0.0,
        max_delay=0.01,
        sleep=lambda s: None,
    )


def usage_rows(llm: LLM) -> list[dict]:
    return [json.loads(line) for line in llm.usage_path.read_text().splitlines()]


MSG = [{"role": "user", "content": "Say OK."}]


# ------------------------------------------------------------------ chat
def test_chat_returns_content_usage_and_logs(llm, api):
    r = llm.chat(MSG, stage="smoke", max_tokens=5)
    assert r.content == "echo:Say OK."
    assert r.usage.prompt_tokens == 11 and r.usage.completion_tokens == 4
    assert not r.cached and r.attempts == 1
    row = usage_rows(llm)[-1]
    assert (
        row["run"] == "test" and row["stage"] == "smoke" and row["endpoint"] == "chat"
    )
    assert (
        row["model"] == "Qwen/Qwen3-8B"
        and row["prompt_tokens"] == 11
        and row["error"] is None
    )


def test_each_endpoint_uses_its_own_key(llm, api):
    llm.chat(MSG, stage="s")
    llm.embed(["a"], stage="s")
    assert api.chat_calls()[0]["auth"] == "Bearer test-chat-key"
    assert api.embed_calls()[0]["auth"] == "Bearer test-embed-key"


def test_usage_log_has_no_prompts_or_keys(llm):
    llm.chat([{"role": "user", "content": "my passport is X1234567"}], stage="s")
    text = llm.usage_path.read_text()
    assert "X1234567" not in text and "test-chat-key" not in text


def test_endpoint_repr_hides_key():
    ep = Endpoint("chat", "https://h/v1", "test-secret-key", model="m")
    assert "test-secret-key" not in repr(ep)


def test_tool_calls_are_parsed(llm):
    tools = [
        {
            "type": "function",
            "function": {
                "name": "determine_exemption",
                "parameters": {"type": "object"},
            },
        }
    ]
    r = llm.chat(MSG, stage="planner", tools=tools)
    assert r.finish_reason == "tool_calls"
    assert r.tool_calls[0].name == "determine_exemption"
    assert r.tool_calls[0].args() == {"trip_hours": 240}


# ----------------------------------------------------------------- cache
def test_identical_call_is_served_from_cache(llm, api):
    first = llm.chat(MSG, stage="s")
    second = llm.chat(MSG, stage="s")
    assert len(api.chat_calls()) == 1
    assert second.cached and second.content == first.content and second.attempts == 0
    assert usage_rows(llm)[-1]["cached"] is True


def test_cached_tool_calls_round_trip(llm, api):
    tools = [
        {
            "type": "function",
            "function": {
                "name": "determine_exemption",
                "parameters": {"type": "object"},
            },
        }
    ]
    llm.chat(MSG, stage="p", tools=tools)
    again = llm.chat(MSG, stage="p", tools=tools)
    assert again.cached and again.tool_calls[0].args() == {"trip_hours": 240}


def test_cache_can_be_disabled(llm, api):
    llm.cache_enabled = False
    llm.chat(MSG, stage="s")
    llm.chat(MSG, stage="s")
    assert len(api.chat_calls()) == 2


def test_sampling_without_sample_id_is_not_cached(llm, api):
    llm.chat(MSG, stage="cot", temperature=0.7)
    llm.chat(MSG, stage="cot", temperature=0.7)
    assert len(api.chat_calls()) == 2


def test_sample_ids_get_separate_cache_entries(llm, api):
    for s in (0, 1, 2):
        llm.chat(MSG, stage="cot", temperature=0.7, sample=s)
    for s in (0, 1, 2):
        assert llm.chat(MSG, stage="cot", temperature=0.7, sample=s).cached
    assert len(api.chat_calls()) == 3


def test_different_params_are_different_cache_entries(llm, api):
    llm.chat(MSG, stage="s", max_tokens=5)
    llm.chat(MSG, stage="s", max_tokens=6)
    assert len(api.chat_calls()) == 2


# --------------------------------------------------------------- retries
def test_429_is_retried_honouring_retry_after(llm, api):
    slept: list[float] = []
    llm.sleep = slept.append
    llm.max_delay = 10
    api.error(429, retry_after="2")
    r = llm.chat(MSG, stage="s")
    assert r.content == "echo:Say OK." and r.attempts == 2
    assert slept == [2.0]
    assert len(api.chat_calls()) == 2


def test_5xx_retries_then_gives_up(llm, api):
    llm.max_attempts = 3
    for _ in range(3):
        api.error(503)
    with pytest.raises(LLMError) as exc:
        llm.chat(MSG, stage="planner")
    assert (
        exc.value.status == 503
        and exc.value.attempts == 3
        and exc.value.stage == "planner"
    )
    assert usage_rows(llm)[-1]["error"].endswith(":503")


def test_400_is_not_retried(llm, api):
    api.error(400)
    with pytest.raises(LLMError) as exc:
        llm.chat(MSG, stage="s")
    assert exc.value.status == 400 and exc.value.attempts == 1
    assert len(api.chat_calls()) == 1


def test_failed_call_is_not_cached(llm, api):
    api.error(400)
    with pytest.raises(LLMError):
        llm.chat(MSG, stage="s")
    assert not llm.chat(MSG, stage="s").cached


# ---------------------------------------------------------------- queue
def test_one_request_in_flight_across_threads(llm, api):
    api.delay = 0.05
    llm.cache_enabled = False
    threads = [
        threading.Thread(
            target=llm.chat,
            args=([{"role": "user", "content": str(i)}],),
            kwargs={"stage": "t"},
        )
        for i in range(6)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(api.chat_calls()) == 6
    assert api.max_in_flight == 1


def test_two_clients_share_the_queue_through_the_lock_file(api, tmp_path):
    """Two LLM objects (like two scripts) on the same log dir never overlap."""
    api.delay = 0.05

    def make() -> LLM:
        return LLM(
            chat_endpoint=Endpoint("chat", api.url, "k", model="m"),
            embed_endpoint=Endpoint("embeddings", api.url, "k", model="e"),
            log_dir=tmp_path,
            cache_enabled=False,
        )

    a, b = make(), make()
    threads = [
        threading.Thread(
            target=c.chat,
            args=([{"role": "user", "content": str(i)}],),
            kwargs={"stage": "t"},
        )
        for i, c in enumerate([a, b, a, b])
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert api.max_in_flight == 1


# ---------------------------------------------------------------- budget
def test_max_tokens_over_output_limit_is_refused(llm, api):
    with pytest.raises(BudgetError):
        llm.chat(MSG, stage="s", max_tokens=2000)
    assert api.calls == []


def test_oversized_prompt_is_refused_before_sending(llm, api):
    huge = [{"role": "user", "content": "word " * 8000}]
    with pytest.raises(BudgetError):
        llm.chat(huge, stage="writer", max_tokens=500)
    assert api.calls == []


# ------------------------------------------------------------ embeddings
def test_embeddings_keep_order_and_batch(llm, api):
    llm.embed_batch_size = 2
    texts = ["a", "bb", "ccc", "dddd", "eeeee"]
    vecs = llm.embed(texts, stage="index")
    assert [v[0] for v in vecs] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert all(len(v) == 384 for v in vecs)
    assert [len(c["body"]["input"]) for c in api.embed_calls()] == [2, 2, 1]
    assert api.embed_calls()[0]["body"]["model"] == "bge-small-en-v1.5"


def test_embeddings_cache_per_text(llm, api):
    llm.embed(["a", "bb"], stage="index")
    vecs = llm.embed(["bb", "ccc", "a"], stage="query")
    assert [v[0] for v in vecs] == [2.0, 3.0, 1.0]
    assert [c["body"]["input"] for c in api.embed_calls()] == [["a", "bb"], ["ccc"]]
