"""The budget guard must never under-count. Ground truth: SiliconFlow usage.prompt_tokens
from the Phase 0 spike (docs/results/phase0-spike-siliconflow.json)."""

import pytest

from copilot.llm.budget import count_message_tokens, get_tokenizer

SYSTEM = "You are a concise assistant for Indian public procurement questions. Answer in English."
TOOL = {
    "type": "function",
    "function": {
        "name": "screen_vendor",
        "description": "Look up a firm name in the dated vendor screening snapshot.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Firm name to screen"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
}


@pytest.fixture(scope="module")
def tok():
    try:
        return get_tokenizer("Qwen/Qwen3-8B")
    except Exception as err:  # noqa: BLE001 - offline machine without a cached tokenizer
        pytest.skip(f"tokenizer unavailable: {err}")


def test_plain_messages_not_undercounted(tok):
    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "In one sentence, what is the GeM portal?"},
    ]
    est = count_message_tokens(tok, msgs)
    assert 43 <= est <= 43 + 10  # actual: 43


def test_tool_prompt_not_undercounted(tok):
    msgs = [
        {"role": "system", "content": SYSTEM + " Use tools when a lookup is needed."},
        {"role": "user", "content": "Is the firm 'DNS OVERSEAS' on any screening list?"},
    ]
    est = count_message_tokens(tok, msgs, [TOOL])
    assert 212 <= est <= 212 + 20  # actual: 212
