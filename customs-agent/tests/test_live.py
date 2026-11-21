"""Live tests: src/llm.py against the real chat and embeddings endpoints.

Not part of the normal run. They make about 8 small calls, one at a time:

    uv run pytest -m live -v

Calls are logged to logs/usage.jsonl under run "live-tests".
"""

from __future__ import annotations

import json
import math

import pytest

from src.endpoints import ConfigError, Endpoint
from src.llm import LLM, BudgetError, LLMError

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def llm() -> LLM:
    try:
        return LLM.from_env(run_name="live-tests", cache_enabled=False)
    except ConfigError as e:
        pytest.skip(f"endpoint settings missing: {e}")


@pytest.fixture(scope="module")
def hello(llm):
    """One shared chat call for the basic checks."""
    return llm.chat(
        [{"role": "user", "content": "Reply with the single word OK."}],
        stage="live-hello",
        max_tokens=10,
    )


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


# ------------------------------------------------------------------ chat
def test_chat_endpoint_replies(hello):
    assert hello.content and "ok" in hello.content.lower()


def test_chat_reports_token_usage(hello):
    assert hello.usage.prompt_tokens and hello.usage.prompt_tokens > 0
    assert hello.usage.completion_tokens is not None


def test_chat_model_is_the_pinned_one(llm, hello):
    assert llm.chat_model.split("/")[-1].lower() in hello.model.lower()


def test_native_tool_call(llm):
    """The model passes durations as stated (value + unit); code converts to hours.

    Asked for `trip_hours` directly, Qwen3-8B copied "10" from "10 days"
    (COMPENSATIONS.md row 3), so tool schemas never ask the model to convert units.
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "determine_exemption",
                "description": "Work out which US customs personal exemption applies.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "trip_duration": {
                            "type": "object",
                            "description": "Time spent abroad, exactly as the traveller stated it",
                            "properties": {
                                "value": {"type": "number"},
                                "unit": {
                                    "type": "string",
                                    "enum": ["hours", "days", "weeks"],
                                },
                            },
                            "required": ["value", "unit"],
                        }
                    },
                    "required": ["trip_duration"],
                },
            },
        }
    ]
    r = llm.chat(
        [
            {
                "role": "user",
                "content": "I was abroad for 10 days. Which exemption applies?",
            }
        ],
        stage="live-tools",
        tools=tools,
        tool_choice="auto",
        max_tokens=200,
    )
    assert r.tool_calls, f"no tool call; model replied {r.content!r}"
    assert r.tool_calls[0].name == "determine_exemption"
    duration = r.tool_calls[0].args()["trip_duration"]
    assert duration["value"] == 10 and duration["unit"] == "days"


def test_json_schema_output(llm):
    schema = {
        "type": "object",
        "properties": {
            "item": {"type": "string"},
            "quantity": {"type": "integer"},
            "unit": {"type": "string", "enum": ["ml", "l", "cigarettes", "cigars"]},
        },
        "required": ["item", "quantity", "unit"],
        "additionalProperties": False,
    }
    r = llm.chat(
        [
            {
                "role": "user",
                "content": "Extract the purchase: 'I bought 2 cartons of cigarettes.'",
            }
        ],
        stage="live-json",
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "purchase", "schema": schema},
        },
        max_tokens=100,
    )
    data = json.loads(r.content)
    assert set(data) == {"item", "quantity", "unit"}
    assert data["unit"] in {"ml", "l", "cigarettes", "cigars"}


# ------------------------------------------------------------ embeddings
def test_embeddings_have_384_dimensions(llm):
    [vec] = llm.embed(["duty-free allowance for wine"], stage="live-embed")
    assert len(vec) == 384


def test_embeddings_rank_related_text_closer(llm):
    wine, wine_limit, cigars = llm.embed(
        [
            "How much wine can I bring back duty free?",
            "Alcohol allowance for returning US residents",
            "Ban on importing Cuban cigars",
        ],
        stage="live-embed-batch",
    )
    assert cosine(wine, wine_limit) > cosine(wine, cigars)


# ------------------------------------------------------- client behaviour
def test_repeat_call_served_from_cache(tmp_path):
    cached = LLM.from_env(run_name="live-tests", log_dir=tmp_path, cache_enabled=True)
    msg = [{"role": "user", "content": "Reply with the single word OK."}]
    first = cached.chat(msg, stage="live-cache", max_tokens=10)
    second = cached.chat(msg, stage="live-cache", max_tokens=10)
    assert not first.cached and second.cached
    assert second.content == first.content


def test_unknown_model_fails_fast_without_retries(llm):
    bad = Endpoint(
        name="chat",
        base_url=llm.chat_endpoint.base_url,
        api_key=llm.chat_endpoint.api_key,
        model="no-such-model",
        ca_cert=llm.chat_endpoint.ca_cert,
    )
    probe = LLM(
        chat_endpoint=bad,
        embed_endpoint=llm.embed_endpoint,
        run_name="live-tests",
        log_dir=llm.log_dir,
        cache_enabled=False,
    )
    with pytest.raises(LLMError) as exc:
        probe.chat(
            [{"role": "user", "content": "hi"}], stage="live-bad-model", max_tokens=5
        )
    assert exc.value.attempts == 1
    assert exc.value.status is not None and 400 <= exc.value.status < 500


def test_oversized_request_refused_before_sending(llm):
    with pytest.raises(BudgetError):
        llm.chat(
            [{"role": "user", "content": "word " * 8000}],
            stage="live-budget",
            max_tokens=500,
        )


def test_calls_are_logged_without_prompts(llm, hello):
    rows = [json.loads(line) for line in llm.usage_path.read_text().splitlines()]
    mine = [r for r in rows if r["run"] == "live-tests"]
    assert any(r["stage"] == "live-hello" and r["prompt_tokens"] for r in mine)
    assert "single word OK" not in llm.usage_path.read_text()
