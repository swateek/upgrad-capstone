"""The chat call every node uses: explicit max_tokens, budget before sending, strict JSON with
validation and fed-back retries, retry on 429. All offline through httpx.MockTransport."""

import json

import httpx
import pytest
from conftest import chat_response, mock_openai
from pydantic import BaseModel

from customs.llm import ChatClient, MalformedOutput, TokenBudgetExceeded


class Verdict(BaseModel):
    passed: bool
    reason: str


def _client(settings, replies, seen):
    replies = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        status, content = replies.pop(0)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "busy"}})
        return httpx.Response(200, json=chat_response(content))

    return ChatClient(settings, client=mock_openai(handler), sleep=lambda s: None)


def test_request_carries_limits_schema_and_thinking_off(settings):
    seen = []
    chat = _client(settings, [(200, '{"passed": true, "reason": "ok"}')], seen)
    res = chat.complete(
        [{"role": "user", "content": "check"}], max_tokens=200, response_model=Verdict
    )
    body = seen[0]
    assert body["max_tokens"] == 200
    assert body["model"] == "Qwen/Qwen3-8B"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert res.parsed == Verdict(passed=True, reason="ok")
    assert (res.calls, res.prompt_tokens, res.completion_tokens) == (1, 50, 10)


def test_default_max_tokens_is_always_sent(settings):
    seen = []
    _client(settings, [(200, "hi")], seen).complete([{"role": "user", "content": "hi"}])
    assert seen[0]["max_tokens"] == settings.default_max_tokens


def test_prompted_json_mode_for_the_experiment(settings):
    seen = []
    chat = _client(settings, [(200, '{"passed": false, "reason": "x"}')], seen)
    chat.complete([{"role": "user", "content": "c"}], response_model=Verdict, constrained=False)
    assert seen[0]["response_format"] == {"type": "json_object"}


def test_malformed_json_is_retried_with_the_error_fed_back(settings):
    seen = []
    chat = _client(
        settings,
        [(200, "not json"), (200, '{"passed": "maybe"}'), (200, '{"passed": true, "reason": "r"}')],
        seen,
    )
    res = chat.complete([{"role": "user", "content": "c"}], response_model=Verdict)
    assert res.calls == 3 and res.parsed.passed is True
    assert len(res.errors) == 2
    feedback = seen[1]["messages"][-1]["content"]
    assert "not valid" in feedback and "not JSON" in feedback


def test_malformed_after_all_retries_raises_with_usage(settings):
    seen = []
    chat = _client(settings, [(200, "nope")] * 3, seen)
    with pytest.raises(MalformedOutput) as err:
        chat.complete([{"role": "user", "content": "c"}], response_model=Verdict)
    assert err.value.result.calls == 3
    assert err.value.result.prompt_tokens == 150


def test_429_is_retried_through_the_policy(settings):
    seen = []
    chat = _client(settings, [(429, ""), (200, "fine")], seen)
    assert chat.complete([{"role": "user", "content": "c"}]).text == "fine"
    assert len(seen) == 2


def test_budget_is_checked_before_sending(settings):
    seen = []
    chat = _client(settings, [(200, "never")], seen)
    huge = "word " * 9000
    with pytest.raises(TokenBudgetExceeded):
        chat.complete([{"role": "user", "content": huge}], max_tokens=1024)
    assert seen == []


def test_think_blocks_and_fences_are_stripped(settings):
    seen = []
    chat = _client(
        settings, [(200, '<think>hmm</think>```json\n{"passed": true, "reason": "r"}\n```')], seen
    )
    res = chat.complete([{"role": "user", "content": "c"}], response_model=Verdict)
    assert res.parsed.passed is True
