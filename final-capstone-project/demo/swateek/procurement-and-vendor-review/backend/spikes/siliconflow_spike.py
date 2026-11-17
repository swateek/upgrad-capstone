"""Phase 0 spike: what does Qwen3-8B on SiliconFlow actually support?

Raw API calls only (no agent harness). Each check is independent and records what happened.

    uv run python spikes/siliconflow_spike.py

Checks
  1. plain chat, thinking OFF  -> content, no reasoning, usage vs local token estimate
  2. plain chat, thinking left at provider default -> is it ON? what does it cost?
  3. tool call round trip       -> tool_calls present, args valid JSON + schema, `tool` role accepted
  4. response_format json_object
  5. response_format json_schema (strict)
  6. 12-message history         -> docs suggest a 10-message cap
  7. streaming                  -> SSE chunks arrive

Writes docs/results/siliconflow/phase0-spike-siliconflow.json. Never prints the API key.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import openai
from pydantic import BaseModel, ValidationError

from copilot.config import PROJECT_ROOT, get_settings
from copilot.llm import RateGate, call_with_retry, get_provider, make_openai_client
from copilot.llm.budget import count_message_tokens, get_tokenizer

settings = get_settings()
provider = get_provider(settings)
client = make_openai_client(provider, settings.request_timeout_s)
gate = RateGate(provider.max_concurrency, provider.requests_per_minute)
tokenizer = get_tokenizer(settings.tokenizer_id)
URL = f"{provider.base_url}/chat/completions"

SYSTEM = "You are a concise assistant for Indian public procurement questions. Answer in English."


class ScreenArgs(BaseModel):
    name: str


SCREEN_TOOL = {
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

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "citations"],
    "additionalProperties": False,
}


class Answer(BaseModel):
    answer: str
    citations: list[str]


def chat(messages: list[dict[str, Any]], *, thinking: bool | None = False, **kw: Any):
    extra = {} if thinking is None else {"enable_thinking": thinking}
    t0 = time.perf_counter()
    resp = call_with_retry(
        lambda: client.chat.completions.create(
            model=provider.model,
            messages=messages,
            extra_body=extra,
            **kw,
        ),
        provider=provider.name,
        url=URL,
        delays=settings.retry_delays_s,
        gate=gate,
    )
    return resp, round(time.perf_counter() - t0, 2)


def usage_of(resp) -> dict[str, Any]:
    u = resp.usage
    return u.model_dump() if u is not None else {}


def reasoning_of(msg) -> str:
    return (getattr(msg, "reasoning_content", None) or "").strip()


def check_plain_off() -> dict[str, Any]:
    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "In one sentence, what is the GeM portal?"},
    ]
    resp, secs = chat(msgs, thinking=False, max_tokens=200)
    msg = resp.choices[0].message
    est = count_message_tokens(tokenizer, msgs)
    usage = usage_of(resp)
    return {
        "ok": bool(msg.content) and not reasoning_of(msg),
        "latency_s": secs,
        "content": msg.content,
        "reasoning_chars": len(reasoning_of(msg)),
        "content_has_think_tag": "<think>" in (msg.content or ""),
        "usage": usage,
        "local_prompt_estimate": est,
        "estimate_minus_actual": est - usage.get("prompt_tokens", 0),
    }


def check_plain_default() -> dict[str, Any]:
    msgs = [{"role": "user", "content": "In one sentence, what is the GeM portal?"}]
    resp, secs = chat(msgs, thinking=None, max_tokens=256)
    msg = resp.choices[0].message
    return {
        "ok": True,
        "latency_s": secs,
        "thinking_on_by_default": bool(reasoning_of(msg)) or "<think>" in (msg.content or ""),
        "reasoning_chars": len(reasoning_of(msg)),
        "finish_reason": resp.choices[0].finish_reason,
        "usage": usage_of(resp),
    }


def check_tool_round_trip() -> dict[str, Any]:
    msgs: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM + " Use tools when a lookup is needed."},
        {"role": "user", "content": "Is the firm 'DNS OVERSEAS' on any screening list?"},
    ]
    tools = [SCREEN_TOOL]
    est = count_message_tokens(tokenizer, msgs, tools)
    resp, secs = chat(msgs, tools=tools, max_tokens=300)
    msg = resp.choices[0].message
    calls = msg.tool_calls or []
    out: dict[str, Any] = {
        "latency_s": secs,
        "tool_calls": len(calls),
        "finish_reason": resp.choices[0].finish_reason,
        "content_if_no_call": None if calls else msg.content,
        "usage": usage_of(resp),
        "local_prompt_estimate_with_tools": est,
    }
    if not calls:
        out["ok"] = False
        return out
    raw_args = calls[0].function.arguments
    out["tool_name"] = calls[0].function.name
    out["raw_arguments"] = raw_args
    try:
        ScreenArgs.model_validate_json(raw_args)
        out["args_schema_valid"] = True
    except ValidationError as err:
        out["args_schema_valid"] = False
        out["args_error"] = str(err)
    # Round trip: send a fake tool result back using the `tool` role.
    msgs.append(msg.model_dump(exclude_none=True))
    msgs.append(
        {
            "role": "tool",
            "tool_call_id": calls[0].id,
            "content": json.dumps(
                {
                    "status": "present",
                    "source_list": "GeM delisted sellers (GFR Rule 144(xi))",
                    "snapshot_date": "2024-09-03",
                }
            ),
        }
    )
    try:
        resp2, secs2 = chat(msgs, tools=tools, max_tokens=300)
        out["tool_role_accepted"] = True
        out["final_answer"] = resp2.choices[0].message.content
        out["final_latency_s"] = secs2
        out["final_usage"] = usage_of(resp2)
    except openai.APIStatusError as err:
        out["tool_role_accepted"] = False
        out["tool_role_error"] = f"{err.status_code}: {err.message}"
    out["ok"] = bool(out.get("args_schema_valid") and out.get("tool_role_accepted"))
    return out


JSON_PROMPT = [
    {
        "role": "system",
        "content": SYSTEM + ' Reply ONLY with JSON: {"answer": string, "citations": [string]}. '
        "Cite the given ids only.",
    },
    {
        "role": "user",
        "content": "Context [gfr_2017:R149]: GeM purchase is mandatory for goods/services "
        "available on GeM.\n\nQuestion: Must this office buy laptops through GeM?",
    },
]


def _validate_answer(content: str | None) -> tuple[bool, str | None]:
    try:
        Answer.model_validate_json(content or "")
        return True, None
    except ValidationError as err:
        return False, str(err).splitlines()[0]


def check_json_object() -> dict[str, Any]:
    try:
        resp, secs = chat(JSON_PROMPT, response_format={"type": "json_object"}, max_tokens=300)
    except openai.APIStatusError as err:
        return {"ok": False, "accepted": False, "error": f"{err.status_code}: {err.message}"}
    content = resp.choices[0].message.content
    valid, error = _validate_answer(content)
    return {
        "ok": valid,
        "accepted": True,
        "latency_s": secs,
        "schema_valid": valid,
        "error": error,
        "content": content,
    }


def check_json_schema() -> dict[str, Any]:
    fmt = {
        "type": "json_schema",
        "json_schema": {"name": "answer", "schema": ANSWER_SCHEMA, "strict": True},
    }
    try:
        resp, secs = chat(JSON_PROMPT, response_format=fmt, max_tokens=300)
    except openai.APIStatusError as err:
        return {"ok": False, "accepted": False, "error": f"{err.status_code}: {err.message}"}
    content = resp.choices[0].message.content
    valid, error = _validate_answer(content)
    return {
        "ok": valid,
        "accepted": True,
        "latency_s": secs,
        "schema_valid": valid,
        "error": error,
        "content": content,
    }


def check_long_history() -> dict[str, Any]:
    msgs: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM}]
    for i in range(5):
        msgs.append({"role": "user", "content": f"Note {i}: remember the number {i * 7}."})
        msgs.append({"role": "assistant", "content": "Noted."})
    msgs.append(
        {"role": "user", "content": "What number did I give in note 3? Reply with it only."}
    )
    try:
        resp, secs = chat(msgs, max_tokens=20)
    except openai.APIStatusError as err:
        return {
            "ok": False,
            "messages_sent": len(msgs),
            "accepted": False,
            "error": f"{err.status_code}: {err.message}",
        }
    return {
        "ok": True,
        "messages_sent": len(msgs),
        "accepted": True,
        "latency_s": secs,
        "content": resp.choices[0].message.content,
    }


def check_stream() -> dict[str, Any]:
    t0 = time.perf_counter()
    first = None
    chunks = 0
    text = []

    def run():
        return client.chat.completions.create(
            model=provider.model,
            messages=[{"role": "user", "content": "Name three Indian procurement manuals."}],
            max_tokens=120,
            stream=True,
            extra_body={"enable_thinking": False},
        )

    stream = call_with_retry(run, provider=provider.name, url=URL, gate=gate)
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            if first is None:
                first = time.perf_counter() - t0
            chunks += 1
            text.append(chunk.choices[0].delta.content)
    return {
        "ok": chunks > 0,
        "chunks": chunks,
        "time_to_first_token_s": round(first or 0, 2),
        "total_s": round(time.perf_counter() - t0, 2),
        "content": "".join(text),
    }


CHECKS: list[tuple[str, Callable[[], dict[str, Any]]]] = [
    ("1_plain_thinking_off", check_plain_off),
    ("2_plain_thinking_default", check_plain_default),
    ("3_tool_round_trip", check_tool_round_trip),
    ("4_json_object", check_json_object),
    ("5_json_schema_strict", check_json_schema),
    ("6_twelve_message_history", check_long_history),
    ("7_streaming", check_stream),
]


OUT = PROJECT_ROOT / "docs" / "results" / "siliconflow" / "phase0-spike-siliconflow.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        default="",
        help="comma-separated check numbers to (re)run, merged into the existing results file",
    )
    args = parser.parse_args()
    only = {n.strip() for n in args.only.split(",") if n.strip()}

    results: dict[str, Any] = (
        json.loads(OUT.read_text(encoding="utf-8")) if only and OUT.exists() else {"checks": {}}
    )
    results.update(
        run_at=datetime.now(UTC).isoformat(timespec="seconds"),
        provider=provider.name,
        base_url=provider.base_url,
        model=provider.model,
    )
    for name, fn in CHECKS:
        if only and name.split("_", 1)[0] not in only:
            continue
        try:
            results["checks"][name] = fn()
        except Exception as err:  # noqa: BLE001 - record and keep going; this is a spike
            results["checks"][name] = {
                "ok": False,
                "exception": f"{type(err).__name__}: {err}",
                "trace": traceback.format_exc(limit=3),
            }
        r = results["checks"][name]
        print(f"{'PASS' if r.get('ok') else 'FAIL'}  {name}")

    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
