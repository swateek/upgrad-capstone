import socket
import threading
import time

import httpx
import openai
import pytest
from conftest import UpgradCallInTest

from customs.config import Settings
from customs.llm import (
    EndpointNotConfigured,
    RateGate,
    TokenBudgetExceeded,
    call_with_retry,
    chat_endpoint,
    check_budget,
    embedding_endpoint,
    validate_max_tokens,
)
from customs.llm.endpoints import UPGRAD_HOST


def _status_error(code: int) -> openai.APIStatusError:
    req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    return openai.APIStatusError("boom", response=httpx.Response(code, request=req), body=None)


def test_tests_cannot_reach_upgrad():
    with pytest.raises(UpgradCallInTest):
        socket.create_connection((UPGRAD_HOST, 1033), timeout=1)


def test_max_tokens_range():
    assert validate_max_tokens(1024, 1024) == 1024
    with pytest.raises(TokenBudgetExceeded):
        validate_max_tokens(0, 1024)
    with pytest.raises(TokenBudgetExceeded):
        validate_max_tokens(1025, 1024)


def test_budget_window():
    check_budget(7168, 1024, 8192)
    with pytest.raises(TokenBudgetExceeded):
        check_budget(7169, 1024, 8192)


@pytest.mark.parametrize("code", [429, 503])
def test_retries_retryable_then_succeeds(code):
    calls, sleeps = [], []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise _status_error(code)
        return "ok"

    assert call_with_retry(fn, endpoint="t", url="u", sleep=sleeps.append) == "ok"
    assert sleeps == [2.0, 4.0]


def test_retry_gives_up_after_three_delays():
    sleeps = []

    def fn():
        raise _status_error(503)

    with pytest.raises(openai.APIStatusError):
        call_with_retry(fn, endpoint="t", url="u", sleep=sleeps.append)
    assert sleeps == [2.0, 4.0, 8.0]


@pytest.mark.parametrize("code", [400, 401, 404])
def test_non_retryable_fails_immediately(code):
    sleeps = []

    def fn():
        raise _status_error(code)

    with pytest.raises(openai.APIStatusError):
        call_with_retry(fn, endpoint="t", url="u", sleep=sleeps.append)
    assert sleeps == []


def test_gate_allows_one_request_at_a_time():
    gate = RateGate(max_concurrency=1, requests_per_minute=60)
    active, peak = [0], [0]
    lock = threading.Lock()

    def work():
        with gate:
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.02)
            with lock:
                active[0] -= 1

    threads = [threading.Thread(target=work) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 1


def test_chat_endpoint_thinking_off_one_request_and_key_hidden(settings):
    ep = chat_endpoint(settings)
    assert ep.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
    assert ep.max_concurrency == 1
    assert ep.model == "Qwen/Qwen3-8B"
    assert ep.ca_cert.name == "vm05-ca.crt"
    assert "test-chat-key" not in repr(ep)


def test_embedding_endpoint_limits(settings):
    ep = embedding_endpoint(settings)
    assert (ep.batch_size, ep.max_tokens, ep.dimensions) == (16, 512, 384)
    assert ep.ca_cert.name == "vm02-ca.crt"
    assert "test-embed-key" not in repr(ep)


def test_missing_key_is_clear_error():
    s = Settings(_env_file=None, upgrad_chat_api_key=None)
    with pytest.raises(EndpointNotConfigured, match="UPGRAD_CHAT_API_KEY"):
        chat_endpoint(s)


def test_missing_cert_is_clear_error(tmp_path):
    s = Settings(
        _env_file=None, upgrad_chat_api_key="k", upgrad_chat_ca_cert=tmp_path / "missing.crt"
    )
    with pytest.raises(EndpointNotConfigured, match="UPGRAD_CHAT_CA_CERT"):
        chat_endpoint(s)
