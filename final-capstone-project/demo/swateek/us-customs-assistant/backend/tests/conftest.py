"""Shared test setup.

Tests never reach the upgrad course endpoints: every socket connection to the course host fails
the test (also in CI, where no keys exist). Model calls in tests go through httpx.MockTransport.
"""

from __future__ import annotations

import socket
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from openai import OpenAI

from customs.config import Settings
from customs.llm.endpoints import UPGRAD_HOST


class UpgradCallInTest(AssertionError):
    pass


@pytest.fixture(autouse=True)
def _block_upgrad(monkeypatch: pytest.MonkeyPatch) -> None:
    real_connect = socket.socket.connect

    def guarded(self: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else address
        if host == UPGRAD_HOST:
            raise UpgradCallInTest("tests must never call the upgrad endpoints")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)


@pytest.fixture
def settings() -> Settings:
    """Settings that never read the local .env; fake keys, the real CA files in certs/."""
    return Settings(
        _env_file=None,
        upgrad_chat_api_key="test-chat-key",
        upgrad_embed_api_key="test-embed-key",
        langfuse_public_key=None,
        langfuse_secret_key=None,
        redis_url=None,
        qdrant_url=None,
    )


def chat_response(content: str, prompt_tokens: int = 50, completion_tokens: int = 10) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "Qwen/Qwen3-8B",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def mock_openai(handler: Callable[[httpx.Request], httpx.Response]) -> OpenAI:
    return OpenAI(
        base_url="https://upgrad.test/v1",
        api_key="test",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
