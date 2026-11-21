"""Probe the upgrad course endpoints before building on them. One request at a time; keys are
never printed or written.

    uv run python -m copilot.llm.probe            # embeddings, and chat if UPGRAD_CHAT_API_KEY is set
    uv run python -m copilot.llm.probe --skip-chat

Checks what the code relies on:
  embeddings  vector size; 16 texts per request; what 17 texts and a text over 512 tokens do
  chat        model list; Qwen3 thinking off (vLLM `chat_template_kwargs` vs SiliconFlow's top-level
              `enable_thinking`); tool calls; strict json_schema (the critic); streamed usage;
              our prompt-token estimate vs the server's count; max_tokens=1025 is refused
Writes docs/results/upgrad/probe.md and .json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime
from typing import Any

import openai

from copilot.config import get_settings
from copilot.llm.budget import count_message_tokens, get_tokenizer
from copilot.llm.providers import (
    ProviderNotConfigured,
    get_embedding,
    get_provider,
    make_openai_client,
)

THINK = re.compile(r"<think>", re.IGNORECASE)
TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_record",
        "description": "Look up a record by name.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "the record's name"}},
            "required": ["name"],
        },
    },
}
SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "verdict",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"passed": {"type": "boolean"}, "reason": {"type": "string"}},
            "required": ["passed", "reason"],
            "additionalProperties": False,
        },
    },
}


def attempt(name: str, fn) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        out = fn()
        ok = out.pop("_ok", True)
        row = {"check": name, "ok": ok, **out}
    except openai.APIStatusError as e:
        row = {"check": name, "ok": False, "status": e.status_code, "error": str(e.body)[:300]}
    except Exception as e:  # noqa: BLE001 - a probe records every failure
        row = {"check": name, "ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
    row["seconds"] = round(time.perf_counter() - t0, 2)
    print(
        f"{'OK  ' if row['ok'] else 'FAIL'} {name:34s} {row['seconds']:6.2f}s  "
        f"{json.dumps({k: v for k, v in row.items() if k not in ('check', 'ok', 'seconds')})[:150]}"
    )
    return row


def probe_embeddings(settings) -> list[dict[str, Any]]:
    cfg = get_embedding(settings)
    client = make_openai_client(cfg, settings.request_timeout_s)
    tok = get_tokenizer(cfg.tokenizer_id)
    long_text = " ".join(f"Rule {i} applies to the purchase of office supplies." for i in range(80))
    n_long = len(tok.encode(long_text).ids)

    def embed(texts: list[str]) -> dict[str, Any]:
        r = client.embeddings.create(model=cfg.model, input=texts)
        return {
            "vectors": len(r.data),
            "dimensions": len(r.data[0].embedding),
            "usage": r.usage.model_dump() if r.usage else None,
        }

    def rejected(texts: list[str], **extra: Any) -> dict[str, Any]:
        """Over a documented limit: a 422 is the expected answer (the code never sends this)."""
        try:
            out = embed(texts)
        except openai.APIStatusError as e:
            return {
                "expected": "rejected",
                "status": e.status_code,
                "error": str(e.body)[:200],
                "_ok": e.status_code == 422,
                **extra,
            }
        return {"expected": "rejected", "accepted": True, "_ok": False, **extra, **out}

    def oversized() -> dict[str, Any]:
        return rejected([long_text], bge_tokens=n_long)

    def seventeen() -> dict[str, Any]:
        return rejected([f"text {i}" for i in range(17)])

    return [
        attempt("embed: 1 text", lambda: embed(["Example search query"])),
        attempt("embed: 16 texts", lambda: embed([f"chunk {i}" for i in range(16)])),
        attempt("embed: 17 texts (limit 16) is refused", seventeen),
        attempt(f"embed: {n_long}-token text (limit 512) is refused", oversized),
    ]


def probe_chat(settings) -> list[dict[str, Any]]:
    p = get_provider(settings)
    client = make_openai_client(p, settings.request_timeout_s)
    tok = get_tokenizer(settings.tokenizer_id)
    q = [{"role": "user", "content": "In one short sentence: what does a reranker do?"}]

    def chat(messages, extra_body=None, **kw) -> Any:
        return client.chat.completions.create(
            model=p.model, messages=messages, temperature=0, extra_body=extra_body, **kw
        )

    def thinking(extra_body) -> dict[str, Any]:
        r = chat(q, extra_body=extra_body, max_tokens=300)
        msg = r.choices[0].message
        text = msg.content or ""
        reasoning = getattr(msg, "reasoning_content", None) or (msg.model_extra or {}).get(
            "reasoning_content"
        )
        thinks = bool(THINK.search(text) or reasoning)
        return {
            "thinking_seen": thinks,
            "completion_tokens": r.usage.completion_tokens if r.usage else None,
            "finish": r.choices[0].finish_reason,
            "answer": text[:120],
            "_ok": True,
        }

    def models() -> dict[str, Any]:
        return {"models": [m.id for m in client.models.list().data]}

    def estimate() -> dict[str, Any]:
        msgs = [{"role": "system", "content": "You are a helpful assistant."}, *q]
        r = chat(msgs, extra_body=p.extra_body, max_tokens=60)
        est = count_message_tokens(tok, msgs)
        r2 = chat(msgs, extra_body=p.extra_body, max_tokens=60, tools=[TOOL])
        est2 = count_message_tokens(tok, msgs, [TOOL])
        return {
            "server_prompt_tokens": r.usage.prompt_tokens,
            "our_estimate": est,
            "server_with_tool": r2.usage.prompt_tokens,
            "our_estimate_with_tool": est2,
            "_ok": est >= r.usage.prompt_tokens and est2 >= r2.usage.prompt_tokens,
        }

    def tool_call() -> dict[str, Any]:
        msgs = [{"role": "user", "content": "Look up the record named 'Acme Traders'."}]
        r = chat(msgs, extra_body=p.extra_body, max_tokens=200, tools=[TOOL])
        calls = r.choices[0].message.tool_calls or []
        args = json.loads(calls[0].function.arguments) if calls else None
        return {
            "tool_calls": [c.function.name for c in calls],
            "arguments": args,
            "_ok": bool(calls) and calls[0].function.name == "lookup_record" and "name" in args,
        }

    def json_schema() -> dict[str, Any]:
        msgs = [
            {"role": "system", "content": "Review the draft. Reply as JSON."},
            {
                "role": "user",
                "content": "Draft: 'The rule allows purchases up to Rs 50,000 without quotations.'",
            },
        ]
        r = chat(msgs, extra_body=p.extra_body, max_tokens=200, response_format=SCHEMA)
        data = json.loads(r.choices[0].message.content or "")
        return {"parsed": data, "_ok": set(data) == {"passed", "reason"}}

    def stream_usage() -> dict[str, Any]:
        usage, chunks = None, 0
        for ev in chat(
            q,
            extra_body=p.extra_body,
            max_tokens=60,
            stream=True,
            stream_options={"include_usage": True},
        ):
            chunks += 1
            usage = ev.usage or usage
        return {
            "chunks": chunks,
            "usage": usage.model_dump() if usage else None,
            "_ok": bool(usage),
        }

    def max_tokens_cap() -> dict[str, Any]:
        try:
            chat(q, extra_body=p.extra_body, max_tokens=1025)
        except openai.APIStatusError as e:
            return {"status": e.status_code, "_ok": e.status_code == 400}
        return {"accepted": True, "_ok": False}

    return [
        attempt("chat: list models", models),
        attempt("chat: thinking off (chat_template_kwargs)", lambda: thinking(p.extra_body)),
        attempt(
            "chat: thinking off (enable_thinking)",
            lambda: thinking({"enable_thinking": settings.enable_thinking}),
        ),
        attempt("chat: no thinking flag (default)", lambda: thinking(None)),
        attempt("chat: prompt-token estimate", estimate),
        attempt("chat: tool call", tool_call),
        attempt("chat: strict json_schema", json_schema),
        attempt("chat: streamed usage", stream_usage),
        attempt("chat: max_tokens=1025 refused", max_tokens_cap),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-chat", action="store_true")
    args = ap.parse_args()
    settings = get_settings().model_copy(update={"provider": "upgrad"})
    rows = probe_embeddings(settings)
    chat_note = None
    if args.skip_chat:
        chat_note = "skipped (--skip-chat)"
    else:
        try:
            rows += probe_chat(settings)
        except ProviderNotConfigured as e:
            chat_note = f"skipped: {e}"
            print(chat_note)
    meta = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "chat_host": settings.upgrad_chat_base_url.split("/")[2],
        "embed_host": settings.upgrad_embed_base_url.split("/")[2],
        "chat": chat_note or "probed",
    }
    out = settings.results_dir / "probe"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(
        json.dumps({"meta": meta, "rows": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# upgrad endpoint probe",
        "",
        (
            f"{meta['run_at']} · chat `{meta['chat_host']}` · embeddings "
            f"`{meta['embed_host']}` · chat: {meta['chat']}"
        ),
        "",
        "| Check | OK | Seconds | Detail |",
        "|---|---|---|---|",
    ]
    for r in rows:
        detail = {k: v for k, v in r.items() if k not in ("check", "ok", "seconds")}
        cell = json.dumps(detail, ensure_ascii=False).replace("|", "\\|")[:300]
        lines.append(
            f"| {r['check']} | {'yes' if r['ok'] else '**no**'} | {r['seconds']} | {cell} |"
        )
    out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
