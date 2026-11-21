"""Day-0 check of the upgrad course endpoints, after the mentor note "Checking What the Capstone
Endpoint Supports" (mentor-notes/Endpoint_Capability_Check.docx). See PLAN.md.

    uv run check_endpoint.py --dry-run     # settings, certs, clients, tokenizers; nothing sent
    uv run check_endpoint.py               # the full check (about 25 small requests)

Built on the demo's copilot package, so it reaches upgrad the way the demo does: the course CA
certificates (TLS verification on), thinking off, no SDK retries, one active request per key.
Keys and certificates come from THIS folder's .env and certs/, never the demo project's.

Sections
  A  the mentor's checks, with the mentor's prompts: models, tools, json_schema, json_object,
     embeddings, usage
  B  added: forced tool calls (required / named), the embedding server's /info
  C  copilot.llm.probe's chat and embedding checks, unchanged (the 14 Nov probe)

Writes results/endpoint_check.txt and .json, and appends a line to results/quota-log.md.
Keys are never printed or written.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI

from copilot.config import Settings
from copilot.llm import probe
from copilot.llm.budget import get_tokenizer
from copilot.llm.providers import (
    BGE_TOKENIZER,
    EmbeddingConfig,
    Endpoint,
    ProviderConfig,
    ProviderNotConfigured,
    get_embedding,
    get_provider,
    make_http_client,
)

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE / ".env"
RESULTS = HERE / "results"
CONTEXT_BUDGET = 8192  # Track B: input + output per call, enforced by copilot

WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}
WEATHER_Q = [{"role": "user", "content": "What is the weather in Pune?"}]
NO_TOOL_NEEDED = [{"role": "user", "content": "Hi there!"}]
CITY_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "city",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}, "state": {"type": "string"}},
            "required": ["city", "state"],
            "additionalProperties": False,
        },
    },
}


# --- token meter ------------------------------------------------------------------------------


class Meter:
    """Counts requests and the tokens the server reports, from every response body."""

    def __init__(self) -> None:
        self.requests = 0
        self.chat_prompt = 0
        self.chat_completion = 0
        self.embed = 0

    def hook(self, endpoint: Endpoint) -> Callable[[httpx.Response], None]:
        is_embed = isinstance(endpoint, EmbeddingConfig)

        def on_response(r: httpx.Response) -> None:
            self.requests += 1
            if r.request.method != "POST":
                return
            r.read()  # buffered; the SDK still reads the (streamed) body afterwards
            for usage in _usages(r):
                if is_embed:
                    self.embed += usage.get("prompt_tokens") or usage.get("total_tokens") or 0
                else:
                    self.chat_prompt += usage.get("prompt_tokens") or 0
                    self.chat_completion += usage.get("completion_tokens") or 0

        return on_response

    def as_dict(self) -> dict[str, int]:
        return {
            "requests": self.requests,
            "chat_prompt_tokens": self.chat_prompt,
            "chat_completion_tokens": self.chat_completion,
            "embedding_tokens": self.embed,
        }


def _usages(r: httpx.Response) -> list[dict[str, Any]]:
    try:
        if "text/event-stream" in r.headers.get("content-type", ""):
            events = [
                json.loads(line[6:])
                for line in r.text.splitlines()
                if line.startswith("data: ") and line[6:].strip() != "[DONE]"
            ]
        else:
            events = [r.json()]
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    return [e["usage"] for e in events if isinstance(e, dict) and isinstance(e.get("usage"), dict)]


METER = Meter()


def metered_client(endpoint: Endpoint, timeout_s: float) -> OpenAI:
    """copilot's make_openai_client (course CA, gate, max_retries=0) plus the token meter."""
    http = make_http_client(endpoint, timeout_s)
    http.event_hooks = {"request": [], "response": [METER.hook(endpoint)]}
    return OpenAI(
        base_url=endpoint.base_url,
        api_key=endpoint.api_key,
        timeout=timeout_s,
        max_retries=0,
        http_client=http,
    )


# Section C runs copilot.llm.probe unchanged; this makes its requests count in the meter too.
probe.make_openai_client = metered_client


# --- settings ---------------------------------------------------------------------------------


def load_settings() -> Settings:
    """copilot Settings from this folder's .env only; cert paths relative to this folder."""
    if not ENV_FILE.is_file():
        raise ProviderNotConfigured(f"{ENV_FILE} is missing: copy env.sample to .env, add keys.")
    s = Settings(_env_file=ENV_FILE, provider="upgrad", domain="procurement")

    def here(p: Path) -> Path:
        return p if p.is_absolute() else HERE / p

    return s.model_copy(
        update={
            "upgrad_chat_ca_cert": here(s.upgrad_chat_ca_cert),
            "upgrad_embed_ca_cert": here(s.upgrad_embed_ca_cert),
        }
    )


# --- helpers ----------------------------------------------------------------------------------


def _json(text: str | None) -> Any:
    try:
        return json.loads(text or "")
    except json.JSONDecodeError:
        return None


def _host(url: str) -> str:
    return url.split("/")[2]


def fatal(row: dict[str, Any]) -> bool:
    """The endpoint can't be reached or refuses the key: nothing after this would mean anything."""
    if row["ok"]:
        return False
    err = row.get("error", "")
    return row.get("status") in (401, 403) or any(
        s in err for s in ("Connection", "SSL", "Timeout", "certificate")
    )


# --- sections A and B -------------------------------------------------------------------------


def chat_checks(settings: Settings, p: ProviderConfig, repeats: int) -> dict[str, dict]:
    client = metered_client(p, settings.request_timeout_s)

    def chat(messages: list[dict], max_tokens: int = 200, **kw: Any) -> Any:
        return client.chat.completions.create(
            model=p.model,
            messages=messages,
            temperature=0,
            max_tokens=max_tokens,
            extra_body=p.extra_body,
            **kw,
        )

    def models() -> dict[str, Any]:
        data = client.models.list().data
        ids = [m.id for m in data]
        lens = {m.id: (m.model_extra or {}).get("max_model_len") for m in data}
        return {"models": ids, "max_model_len": lens, "configured": p.model, "_ok": p.model in ids}

    def tools_auto() -> dict[str, Any]:
        runs = []
        for _ in range(repeats):
            r = chat(WEATHER_Q, tools=[WEATHER_TOOL], tool_choice="auto")
            calls = r.choices[0].message.tool_calls or []
            if calls:
                fn = calls[0].function
                args = _json(fn.arguments)
                ok = fn.name == "get_weather" and isinstance(args, dict) and "city" in args
                runs.append({"name": fn.name, "arguments": args, "valid": ok})
            else:
                runs.append({"text": (r.choices[0].message.content or "")[:100]})
        called = sum("name" in x for x in runs)
        valid = sum(bool(x.get("valid")) for x in runs)
        return {
            "runs": repeats,
            "called": called,
            "valid_arguments": valid,
            "first": runs[0],
            "_ok": valid == repeats,
        }

    def forced(choice: Any) -> Callable[[], dict[str, Any]]:
        def run() -> dict[str, Any]:
            r = chat(NO_TOOL_NEEDED, tools=[WEATHER_TOOL], tool_choice=choice)
            calls = r.choices[0].message.tool_calls or []
            return {
                "tool_calls": [c.function.name for c in calls],
                "arguments": _json(calls[0].function.arguments) if calls else None,
                "text": None if calls else (r.choices[0].message.content or "")[:100],
                "_ok": bool(calls) and calls[0].function.name == "get_weather",
            }

        return run

    def json_schema() -> dict[str, Any]:
        msgs = [{"role": "user", "content": "Name one Indian city and its state."}]
        r = chat(msgs, response_format=CITY_SCHEMA)
        data = _json(r.choices[0].message.content)
        return {
            "parsed": data,
            "_ok": isinstance(data, dict) and set(data) == {"city", "state"},
        }

    def json_object() -> dict[str, Any]:
        msgs = [
            {
                "role": "user",
                "content": "Reply in JSON with keys city and state for one Indian city.",
            }
        ]
        r = chat(msgs, response_format={"type": "json_object"})
        data = _json(r.choices[0].message.content)
        return {
            "parsed": data,
            "raw": None if data else r.choices[0].message.content[:100],
            "_ok": isinstance(data, dict),
        }

    def usage() -> dict[str, Any]:
        r = chat([{"role": "user", "content": "Say OK."}], max_tokens=5)
        u = r.usage.model_dump() if r.usage else None
        return {
            "usage": u,
            "_ok": bool(u and u.get("prompt_tokens") and u.get("completion_tokens")),
        }

    rows: dict[str, dict] = {}
    rows["models"] = probe.attempt("A1 chat: /models", models)
    if fatal(rows["models"]):
        return rows
    rows["tools"] = probe.attempt(f"A2 chat: tools auto x{repeats}", tools_auto)
    rows["json_schema"] = probe.attempt("A3 chat: json_schema (strict)", json_schema)
    rows["json_object"] = probe.attempt("A4 chat: json_object", json_object)
    rows["usage"] = probe.attempt("A6 chat: usage", usage)
    rows["tool_required"] = probe.attempt("B1 chat: tool_choice=required", forced("required"))
    named = {"type": "function", "function": {"name": "get_weather"}}
    rows["tool_named"] = probe.attempt("B1 chat: tool_choice=named", forced(named))
    return rows


def embed_checks(settings: Settings, e: EmbeddingConfig) -> dict[str, dict]:
    client = metered_client(e, settings.request_timeout_s)

    def models() -> dict[str, Any]:
        ids = [m.id for m in client.models.list().data]
        known = e.model in ids or any(i.endswith("/" + e.model) for i in ids)
        return {"models": ids, "configured": e.model, "_ok": known}

    def one() -> dict[str, Any]:
        r = client.embeddings.create(model=e.model, input=["hello world"])
        return {
            "model": e.model,
            "dimensions": len(r.data[0].embedding),
            "usage": r.usage.model_dump() if r.usage else None,
        }

    def info() -> dict[str, Any]:
        root = e.base_url.rstrip("/").removesuffix("/v1")
        with make_http_client(e, settings.request_timeout_s) as http:
            r = http.get(f"{root}/info", headers={"Authorization": f"Bearer {e.api_key}"})
        if r.status_code == 404:
            return {"available": False, "status": 404}
        r.raise_for_status()
        data = r.json()
        keys = (
            "model_id",
            "model_dtype",
            "max_input_length",
            "max_client_batch_size",
            "max_batch_tokens",
            "version",
        )
        return {"available": True, **{k: data.get(k) for k in keys if k in data}}

    rows: dict[str, dict] = {}
    rows["embed_models"] = probe.attempt("A5 embed: /models", models)
    if fatal(rows["embed_models"]):
        return rows
    rows["embeddings"] = probe.attempt("A5 embed: 1 text", one)
    rows["embed_info"] = probe.attempt("B2 embed: /info (TEI)", info)
    return rows


# --- reading the results (the note's table) ---------------------------------------------------


def mentor_lines(rows: dict[str, dict], repeats: int) -> list[str]:
    """Section A in the mentor script's output format."""
    out: list[str] = []
    if m := rows.get("models"):
        if m["ok"] or m.get("models"):
            out.append(f"models: {m['models']}")
            out.append(f"using: {m['configured']}   max_model_len: {m['max_model_len']}")
        else:
            out.append(f"models: FAILED -> {m.get('status', '')} {m.get('error', '')}")
    if t := rows.get("tools"):
        if "called" not in t:
            out.append(f"tools: NOT supported -> {t.get('status', '')} {t.get('error', '')}")
        elif t["called"]:
            f = t["first"] if "name" in t["first"] else {"name": "?", "arguments": "?"}
            out.append(
                f"tools: OK -> {f['name']}({json.dumps(f['arguments'])})   "
                f"[called {t['called']}/{repeats}, "
                f"valid arguments {t['valid_arguments']}/{repeats}]"
            )
        else:
            out.append(
                f"tools: accepted, but the model answered in text (no tool call) "
                f"in {repeats}/{repeats} runs"
            )
    for key in ("json_schema", "json_object"):
        if r := rows.get(key):
            if r["ok"]:
                out.append(f"{key}: OK -> {r['parsed']}")
            elif "parsed" in r:
                out.append(f"{key}: accepted, but the reply didn't match -> {r['parsed']}")
            else:
                out.append(f"{key}: NOT supported -> {r.get('status', '')} {r.get('error', '')}")
    if r := rows.get("embeddings"):
        if r["ok"]:
            em = rows.get("embed_models", {})
            served = em.get("models") or f"not published (/models {em.get('status', '?')})"
            out.append(
                f"embeddings: OK -> model={r['model']}, dimension={r['dimensions']}   "
                f"[served: {served}]"
            )
        else:
            out.append(f"embeddings: check failed -> {r.get('status', '')} {r.get('error', '')}")
    if r := rows.get("usage"):
        out.append(f"usage reported: {r.get('usage') or r.get('error')}")
    return out


def verdicts(rows: dict[str, dict], probe_rows: list[dict], repeats: int) -> list[str]:
    v: list[str] = []
    m = rows.get("models", {})
    if m.get("models"):
        lens = [n for n in (m.get("max_model_len") or {}).values() if n]
        ctx = (
            f"context length {lens[0]} (copilot budgets {CONTEXT_BUDGET} per call)"
            if lens
            else "context length not reported by /models (ask the programme office)"
        )
        same = "matches" if m["ok"] else "does NOT match"
        v.append(
            f"models: {len(m['models'])} chat model {m['models']}; {same} CHAT_MODEL; {ctx}. "
            "Develop locally on the same family; write the name in SPEC.md."
        )
    t = rows.get("tools", {})
    if "called" in t:
        if t["valid_arguments"] == repeats:
            v.append(
                f"tools: OK in {repeats}/{repeats} runs -> native tool calling; keep the tools "
                "parameter in the planner and still validate arguments with Pydantic."
            )
        elif t["called"]:
            v.append(
                f"tools: called {t['called']}/{repeats} -> native calls work but not every "
                "time; keep validation and retries on tool calls."
            )
        else:
            v.append(
                f"tools: no call in {repeats}/{repeats} runs -> treat as unsupported: ask for "
                'tool calls as JSON text ({"tool": ..., "args": ...}), parse, validate, retry '
                "up to 2 times; tell the mentor."
            )
    elif t:
        v.append(
            "tools: NOT supported -> JSON-text tool calls, parse and validate, retry up to 2 times."
        )
    req, named = rows.get("tool_required", {}), rows.get("tool_named", {})
    if req or named:
        v.append(
            f"forced tool calls: required {'OK' if req.get('ok') else 'no'}, named "
            f"{'OK' if named.get('ok') else 'no'} -> "
            + (
                "the planner can force a call when a step must use a tool."
                if req.get("ok") and named.get("ok")
                else "don't rely on tool_choice to force a call."
            )
        )
    js, jo = rows.get("json_schema", {}), rows.get("json_object", {})
    if js.get("ok"):
        v.append(
            "json_schema: OK -> constrained decoding is available: use it for the planner, "
            "writer and critic outputs; record 'with vs. without' as an experiment."
        )
    elif jo.get("ok"):
        v.append("only json_object: OK -> JSON mode plus Pydantic validation and retries.")
    elif js or jo:
        v.append(
            "neither JSON mode works -> few-shot JSON examples, Pydantic validation, retry with "
            "the error message."
        )
    if (e := rows.get("embeddings", {})).get("ok"):
        v.append(
            f"embeddings: OK -> configure the vector store with dimension {e['dimensions']} "
            f"(model {e['model']})."
        )
    em, i = rows.get("embed_models", {}), rows.get("embed_info", {})
    if em and not em.get("models") and not i.get("available"):
        v.append(
            "embedding model name: the server publishes none (/v1/models and /info answer "
            f"{em.get('status', 'error')} and {i.get('status', 'error')}); it accepted "
            f"'{e.get('model')}', but that does not prove which model it is. The dimension "
            "fits bge-small-en-v1.5; ask the programme office to confirm the name (Q2)."
        )
    if i.get("available"):
        v.append(
            f"embedding limits from /info: max_input_length={i.get('max_input_length')}, "
            f"max_client_batch_size={i.get('max_client_batch_size')} (copilot uses 512 and 16)."
        )
    if rows.get("usage", {}).get("ok"):
        v.append(
            "usage reported: token counting works -> log prompt_tokens and completion_tokens "
            "per call for the cost metric and the quota log."
        )
    if probe_rows:
        bad = [r["check"] for r in probe_rows if not r["ok"]]
        v.append(
            f"known behaviour (14 Nov probe): {len(probe_rows) - len(bad)}/{len(probe_rows)} as "
            "before" + (f"; changed: {bad}" if bad else ".")
        )
    return v


# --- output -----------------------------------------------------------------------------------


def row_line(r: dict[str, Any]) -> str:
    detail = {k: v for k, v in r.items() if k not in ("check", "ok", "seconds")}
    return (
        f"{'OK  ' if r['ok'] else 'FAIL'} {r['check']:42s} {r['seconds']:6.2f}s  "
        f"{json.dumps(detail, ensure_ascii=False)[:240]}"
    )


def write_results(
    meta: dict[str, Any],
    rows: dict[str, dict],
    probe_rows: list[dict],
    verdict: list[str],
    repeats: int,
) -> None:
    RESULTS.mkdir(exist_ok=True)
    added = [rows[k] for k in ("tool_required", "tool_named", "embed_info") if k in rows]
    tok = meta["tokens"]
    lines = [
        "Endpoint capability check (mentor note: Day 0, checking what the capstone endpoint "
        "supports)",
        f"run at: {meta['run_at']}   by: {meta['by']}",
        f"chat:   {meta['chat_host']}   embeddings: {meta['embed_host']}",
        f"usage:  {tok['requests']} requests; chat {tok['chat_prompt_tokens']} prompt + "
        f"{tok['chat_completion_tokens']} completion tokens; embeddings "
        f"{tok['embedding_tokens']} tokens",
        "",
        "== A. Mentor's checks ==",
        *mentor_lines(rows, repeats),
        "",
        "== B. Added checks ==",
        *(row_line(r) for r in added),
        "",
        "== C. Known behaviour (copilot.llm.probe, unchanged) ==",
        *(row_line(r) for r in probe_rows),
        *([] if probe_rows else ["(skipped)"]),
        "",
        "== Verdict (the note's 'Reading the results' table) ==",
        *(f"- {line}" for line in verdict),
        "",
    ]
    (RESULTS / "endpoint_check.txt").write_text("\n".join(lines), encoding="utf-8")
    (RESULTS / "endpoint_check.json").write_text(
        json.dumps(
            {"meta": meta, "checks": rows, "probe": probe_rows, "verdict": verdict},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    log = RESULTS / "quota-log.md"
    if not log.exists():
        log.write_text(
            "# Quota log (upgrad course endpoints)\n\n"
            "| Date (UTC) | Who | What ran | Requests | Chat tokens (prompt + completion) "
            "| Embedding tokens |\n|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    with log.open("a", encoding="utf-8") as f:
        f.write(
            f"| {meta['run_at']} | {meta['by']} | check_endpoint.py {meta['args']} "
            f"| {tok['requests']} | {tok['chat_prompt_tokens']} + "
            f"{tok['chat_completion_tokens']} | {tok['embedding_tokens']} |\n"
        )
    print(f"\nwrote {RESULTS / 'endpoint_check.txt'} (+ .json) and appended {log.name}")


# --- main -------------------------------------------------------------------------------------


def dry_run(settings: Settings) -> None:
    p, e = get_provider(settings, "upgrad"), get_embedding(settings)
    print(f"env file: {ENV_FILE}")
    for ep in (p, e):
        client = metered_client(ep, settings.request_timeout_s)  # loads the CA into an SSL context
        client.close()
        inside = ep.ca_cert is not None and ep.ca_cert.is_relative_to(HERE)
        print(
            f"{ep.name:13s} {ep.base_url}  model={ep.model}  key=set  "
            f"ca={ep.ca_cert} ({'this folder' if inside else 'OUTSIDE this folder'})  "
            f"max_concurrency={ep.max_concurrency}"
        )
    print(f"chat extra_body: {p.extra_body}")
    for tid in (settings.tokenizer_id, BGE_TOKENIZER):
        get_tokenizer(tid)
        print(f"tokenizer ok: {tid}")
    print(f"requests sent: {METER.requests}  (dry run: nothing goes to upgrad)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="no network calls to upgrad")
    ap.add_argument("--skip-chat", action="store_true")
    ap.add_argument("--skip-embed", action="store_true")
    ap.add_argument("--skip-probe", action="store_true", help="leave out section C")
    ap.add_argument("--tool-repeats", type=int, default=5)
    ap.add_argument("--who", default=getpass.getuser(), help="name for the quota log")
    args = ap.parse_args()

    try:
        settings = load_settings()
        p, e = get_provider(settings, "upgrad"), get_embedding(settings)
        if args.dry_run:
            dry_run(settings)
            return 0
    except ProviderNotConfigured as err:
        print(f"setup error: {err}", file=sys.stderr)
        return 1

    rows: dict[str, dict] = {}
    if not args.skip_chat:
        rows |= chat_checks(settings, p, args.tool_repeats)
    if not args.skip_embed:
        rows |= embed_checks(settings, e)
    unreachable = [r["check"] for r in rows.values() if fatal(r)]

    probe_rows: list[dict] = []
    if not args.skip_probe and not unreachable:
        if not args.skip_embed:
            probe_rows += probe.probe_embeddings(settings)
        if not args.skip_chat:
            probe_rows += probe.probe_chat(settings)

    skips = ("skip_chat", "skip_embed", "skip_probe")
    flags = ["--" + k.replace("_", "-") for k in skips if getattr(args, k)]
    flags += [f"--tool-repeats {args.tool_repeats}"] if args.tool_repeats != 5 else []
    meta = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "by": args.who,
        "args": " ".join(flags) or "(full)",
        "chat_host": _host(p.base_url),
        "embed_host": _host(e.base_url),
        "chat_model": p.model,
        "embed_model": e.model,
        "tokens": METER.as_dict(),
    }
    verdict = verdicts(rows, probe_rows, args.tool_repeats)
    print("\n" + "\n".join(mentor_lines(rows, args.tool_repeats)))
    write_results(meta, rows, probe_rows, verdict, args.tool_repeats)
    if unreachable:
        print(f"endpoint not usable: {unreachable}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
