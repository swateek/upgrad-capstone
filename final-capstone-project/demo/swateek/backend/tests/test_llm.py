import httpx
import openai
import pytest

from copilot.config import Settings
from copilot.llm import (
    TokenBudgetExceeded,
    call_with_retry,
    check_budget,
    get_provider,
    validate_max_tokens,
)
from copilot.llm.providers import ProviderNotConfigured


def _status_error(code: int) -> openai.APIStatusError:
    req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    return openai.APIStatusError("boom", response=httpx.Response(code, request=req), body=None)


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

    assert call_with_retry(fn, provider="t", url="u", sleep=sleeps.append) == "ok"
    assert sleeps == [2.0, 4.0]


def test_retry_gives_up_after_three_delays():
    sleeps = []

    def fn():
        raise _status_error(503)

    with pytest.raises(openai.APIStatusError):
        call_with_retry(fn, provider="t", url="u", sleep=sleeps.append)
    assert sleeps == [2.0, 4.0, 8.0]


@pytest.mark.parametrize("code", [400, 401, 404])
def test_non_retryable_fails_immediately(code):
    sleeps = []

    def fn():
        raise _status_error(code)

    with pytest.raises(openai.APIStatusError):
        call_with_retry(fn, provider="t", url="u", sleep=sleeps.append)
    assert sleeps == []


def test_siliconflow_sends_thinking_off_and_hides_key():
    s = Settings(_env_file=None, domain="test", siliconflow_api_key="sk-test-secret")
    p = get_provider(s)
    assert p.extra_body == {"enable_thinking": False}
    assert "sk-test-secret" not in repr(p)


def test_missing_key_is_clear_error():
    with pytest.raises(ProviderNotConfigured):
        get_provider(Settings(_env_file=None, domain="test", siliconflow_api_key=None))
