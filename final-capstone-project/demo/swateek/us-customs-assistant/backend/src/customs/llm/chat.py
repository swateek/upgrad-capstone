"""One chat call, done the Track B way. Every agent node, baseline and the listwise reranker use it.

- max_tokens is always explicit and within 1..1024
- the prompt is counted before sending: input + max_tokens must fit the 8,192-token window
- 429/503 retried at 2, 4, 8 s through the endpoint's gate (one active request per key)
- structured output: strict json_schema (constrained decoding, confirmed on the endpoint)
  or prompted JSON (for the "with vs without" experiment); the reply is validated with
  Pydantic, and a malformed reply is retried with the error fed back (JSON_RETRIES), then
  MalformedOutput is raised so the caller can escalate
- Qwen3 <think> blocks are stripped if they ever appear
- usage, attempts and seconds are returned for the trace, the quota log and the cost metric
"""

from __future__ import annotations

import json
import re
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from customs.config import Settings
from customs.llm.budget import (
    check_budget,
    count_message_tokens,
    get_tokenizer,
    validate_max_tokens,
)
from customs.llm.endpoints import ChatEndpoint, chat_endpoint, make_openai_client
from customs.llm.retry import call_with_retry
from customs.observability.tracing import Tracer

THINK = re.compile(r"<think>.*?(</think>|$)", re.DOTALL)
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


class MalformedOutput(RuntimeError):
    """The model's reply stayed invalid after every JSON retry."""

    def __init__(self, message: str, result: ChatResult) -> None:
        super().__init__(message)
        self.result = result  # usage still counts toward the question's budget


@dataclass
class ChatResult:
    text: str
    parsed: BaseModel | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0  # model calls made, including JSON retries
    seconds: float = 0.0
    finish_reason: str | None = None
    errors: list[str] = field(default_factory=list)  # validation errors fed back
    message: Any = None  # the raw assistant message (tool calls live here)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def schema_format(model: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": model.__name__,
            "schema": model.model_json_schema(),
            "strict": True,
        },
    }


def clean(text: str) -> str:
    return FENCE.sub("", THINK.sub("", text).strip()).strip()


class ChatClient:
    def __init__(
        self,
        settings: Settings,
        endpoint: ChatEndpoint | None = None,
        client: OpenAI | None = None,
        tracer: Tracer | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self.settings = settings
        self.tracer = tracer
        self.endpoint = endpoint or chat_endpoint(settings)
        self.client = client or make_openai_client(self.endpoint, settings.request_timeout_s)
        self.url = f"{self.endpoint.base_url}/chat/completions"
        self.tok = get_tokenizer(settings.tokenizer_id)
        self._sleep = sleep

    def _create(self, name: str, messages: list[dict[str, Any]], max_tokens: int, **kw: Any) -> Any:
        prompt = count_message_tokens(self.tok, messages, kw.get("tools"))
        check_budget(prompt, max_tokens, self.settings.context_window_tokens)
        with self._generation(name, messages) as gen:
            resp = call_with_retry(
                lambda: self.client.chat.completions.create(
                    model=self.endpoint.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    extra_body=self.endpoint.extra_body,
                    **kw,
                ),
                endpoint=self.endpoint.name,
                url=self.url,
                delays=self.settings.retry_delays_s,
                sleep=self._sleep,
            )
            if gen is not None:
                usage = resp.usage
                gen.update(
                    output=resp.choices[0].message.content,
                    model_parameters={"max_tokens": max_tokens, **_params(kw)},
                    usage_details={
                        "input": usage.prompt_tokens if usage else 0,
                        "output": usage.completion_tokens if usage else 0,
                    },
                )
        return resp

    def _generation(self, name: str, messages: list[dict[str, Any]]) -> Any:
        if self.tracer is None:
            return nullcontext(None)
        return self.tracer.generation(name, self.endpoint.model, messages)

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        response_model: type[BaseModel] | None = None,
        constrained: bool = True,
        temperature: float = 0.0,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        name: str = "chat",
    ) -> ChatResult:
        """One logical call. With response_model, the reply is parsed and validated; invalid
        replies are retried up to settings.json_retries times with the error fed back."""
        max_tokens = validate_max_tokens(
            max_tokens or self.settings.default_max_tokens, self.settings.max_output_tokens
        )
        kw: dict[str, Any] = {"temperature": temperature}
        if tools:
            kw["tools"] = tools
            if tool_choice is not None:
                kw["tool_choice"] = tool_choice
        if response_model is not None:
            kw["response_format"] = (
                schema_format(response_model) if constrained else {"type": "json_object"}
            )

        result = ChatResult(text="")
        convo = list(messages)
        t0 = time.perf_counter()
        for attempt in range(self.settings.json_retries + 1):
            resp = self._create(name, convo, max_tokens, **kw)
            result.calls += 1
            if resp.usage:
                result.prompt_tokens += resp.usage.prompt_tokens or 0
                result.completion_tokens += resp.usage.completion_tokens or 0
            choice = resp.choices[0]
            result.finish_reason = choice.finish_reason
            result.text = clean(choice.message.content or "")
            if response_model is None:
                result.seconds = round(time.perf_counter() - t0, 3)
                result.message = choice.message
                return result
            try:
                result.parsed = response_model.model_validate(json.loads(result.text))
                result.seconds = round(time.perf_counter() - t0, 3)
                return result
            except (json.JSONDecodeError, ValidationError) as err:
                problem = _describe(err)
                result.errors.append(problem)
                if attempt == self.settings.json_retries:
                    break
                convo = [
                    *messages,
                    {"role": "assistant", "content": result.text},
                    {
                        "role": "user",
                        "content": f"That reply was not valid ({problem}). Reply again with "
                        "only the JSON object that matches the schema.",
                    },
                ]
        result.seconds = round(time.perf_counter() - t0, 3)
        raise MalformedOutput(
            f"reply invalid after {result.calls} calls: {result.errors[-1]}", result
        )


def _params(kw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"temperature": kw.get("temperature")}
    if "response_format" in kw:
        out["response_format"] = kw["response_format"]["type"]
    if "tools" in kw:
        out["tools"] = [t["function"]["name"] for t in kw["tools"]]
    return out


def _describe(err: json.JSONDecodeError | ValidationError) -> str:
    if isinstance(err, json.JSONDecodeError):
        return f"not JSON: {err.msg}"
    return "; ".join(
        f"{'.'.join(str(x) for x in e['loc']) or 'reply'}: {e['msg']}" for e in err.errors()
    )
