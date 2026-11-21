"""Per-call token budget: input + max_tokens must fit in the Track B window (8,192)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from tokenizers import Tokenizer

# Calibrated against SiliconFlow usage.prompt_tokens in the Phase 0 spike (12 Nov 2026):
#   2 plain messages: estimate must reach 43 (was 39 with 5/msg) -> 7 per message.
#   same + 1 tool:    actual 212 vs 128 -> Qwen's tool template adds ~85 tokens of fixed text
#                     ("# Tools ... <tools></tools> ... <tool_call>" instructions).
# Errs slightly high on purpose: under-counting would let a call overflow the 8K window.
PER_MESSAGE_OVERHEAD = 7
REPLY_PRIMER = 3
TOOLS_TEMPLATE_OVERHEAD = 85


class TokenBudgetExceeded(ValueError):
    pass


@lru_cache(maxsize=4)
def get_tokenizer(tokenizer_id: str) -> Tokenizer:
    # Downloads tokenizer.json only (no model weights, no PyTorch); cached by the HF cache.
    return Tokenizer.from_pretrained(tokenizer_id)


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def count_message_tokens(
    tokenizer: Tokenizer,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> int:
    """Estimate prompt tokens. Exact counts come back in the response's usage field."""
    total = REPLY_PRIMER
    for msg in messages:
        text = _content_text(msg.get("content"))
        if msg.get("tool_calls"):
            text += json.dumps(msg["tool_calls"], ensure_ascii=False)
        total += PER_MESSAGE_OVERHEAD + len(tokenizer.encode(text).ids)
    if tools:
        total += TOOLS_TEMPLATE_OVERHEAD
        total += len(tokenizer.encode(json.dumps(tools, ensure_ascii=False)).ids)
    return total


def validate_max_tokens(max_tokens: int, ceiling: int) -> int:
    if not 1 <= max_tokens <= ceiling:
        raise TokenBudgetExceeded(f"max_tokens must be between 1 and {ceiling}, got {max_tokens}")
    return max_tokens


def check_budget(prompt_tokens: int, max_tokens: int, window: int) -> None:
    if prompt_tokens + max_tokens > window:
        raise TokenBudgetExceeded(
            f"prompt ({prompt_tokens}) + max_tokens ({max_tokens}) exceeds the {window}-token window"
        )
