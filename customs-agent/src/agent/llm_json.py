"""One JSON call to the chat model, validated with pydantic, with the repair loop from CLAUDE.md:
malformed JSON -> up to 2 retries with the validation error fed back -> StepError (caller escalates)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

MAX_REPAIRS = 2


class StepError(Exception):
    """A model step failed after its retries."""


@dataclass
class Usage:
    calls: int = 0
    tokens: int = 0
    steps: list[dict] = field(
        default_factory=list
    )  # raw outputs, for traces and failure review


def schema_format(model: type[BaseModel]) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {"name": model.__name__, "schema": model.model_json_schema()},
    }


def parse(model: type[BaseModel], text: str | None) -> BaseModel:
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    return model.model_validate_json(raw)


def json_call(
    llm: Any,
    usage: Usage,
    model: type[BaseModel],
    messages: list[dict],
    *,
    stage: str,
    max_tokens: int = 700,
    temperature: float = 0.0,
) -> BaseModel:
    msgs = list(messages)
    last = ""
    for attempt in range(1 + MAX_REPAIRS):
        r = llm.chat(
            msgs,
            stage=stage if attempt == 0 else f"{stage}_repair",
            response_format=schema_format(model),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        usage.calls += 1
        usage.tokens += int(getattr(getattr(r, "usage", None), "total_tokens", 0) or 0)
        usage.steps.append({"stage": stage, "attempt": attempt, "content": r.content})
        try:
            return parse(model, r.content)
        except ValidationError as e:
            err = e.errors()[0]
            last = f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
            msgs = [
                *messages,
                {"role": "assistant", "content": r.content or ""},
                {
                    "role": "user",
                    "content": f"That JSON is invalid ({last}). Return the corrected JSON only.",
                },
            ]
    raise StepError(f"{stage}: invalid JSON after {MAX_REPAIRS} repairs ({last})")
