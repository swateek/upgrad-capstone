"""A scripted chat model for offline agent tests: replays AIMessages in order, records requests."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedChatModel(BaseChatModel):
    script: list[AIMessage] = Field(default_factory=list)
    calls: list[list[Any]] = Field(default_factory=list)
    position: dict[str, int] = Field(default_factory=lambda: {"i": 0})

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):  # tools are irrelevant: the script decides
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.calls.append(list(messages))
        i = self.position["i"]
        if i >= len(self.script):
            raise AssertionError(f"script exhausted after {i} model calls")
        self.position["i"] = i + 1
        msg = self.script[i].model_copy(
            update={
                "usage_metadata": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
            }
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])


def call(name: str, args: dict[str, Any], cid: str) -> dict[str, Any]:
    return {"name": name, "args": args, "id": cid, "type": "tool_call"}
