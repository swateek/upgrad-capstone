"""Day-0 check of the capstone endpoints: chat model, tool calling, JSON output,
embeddings and token usage. Writes the results to a markdown report.

The chat (LLM) and embeddings endpoints are configured separately: each has
its own URL, API key and CA certificate.

Setup:
    uv sync                       # from customs-agent/; installs openai + python-dotenv (.env support)
    # Chat / LLM endpoint
    export CHAT_BASE_URL="https://<llm-endpoint>/v1"
    export CHAT_API_KEY="<llm-key>"                    # never commit keys
    export CHAT_CA_CERT="/path/to/llm_ca_cert.pem"
    export CHAT_MODEL="<chat-model>"                   # optional; default = first model listed
    # Embeddings endpoint
    export EMBED_BASE_URL="https://<embeddings-endpoint>/v1"
    export EMBED_API_KEY="<embeddings-key>"
    export EMBED_CA_CERT="/path/to/embed_ca_cert.pem"
    export EMBED_MODEL="<embeddings-model>"            # optional; default = first model listed
    # Only if an endpoint also needs a client certificate (mutual TLS):
    #   CHAT_CLIENT_CERT / CHAT_CLIENT_KEY, EMBED_CLIENT_CERT / EMBED_CLIENT_KEY
    # Only if Python rejects a CA with "does not include key usage extension":
    #   CA_RELAX_STRICT=1

Run:
    uv run python prechecks/check_endpoint.py                       # writes docs/endpoint_check.md
    uv run python prechecks/check_endpoint.py --out report.md --tool-tries 5
    uv run python prechecks/check_endpoint.py --only embeddings     # re-check one endpoint

The script makes about 9 small calls, one at a time (each endpoint allows only
one request in flight). Record the run in the quota log.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import ssl
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from openai import DefaultHttpxClient, OpenAI

try:  # optional: read settings from a .env file in the current folder
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ------------------------------------------------------------ configuration
@dataclass
class Endpoint:
    """Connection settings for one endpoint. Reuse this and make_client() in src/llm.py."""
    name: str                       # "chat" or "embeddings"
    base_url: str
    api_key: str
    ca_cert: str | None = None
    client_cert: str | None = None
    client_key: str | None = None

    @classmethod
    def from_env(cls, name: str, prefix: str) -> "Endpoint":
        base_url = os.environ.get(f"{prefix}_BASE_URL")
        api_key = os.environ.get(f"{prefix}_API_KEY")
        if not base_url or not api_key:
            sys.exit(f"Set {prefix}_BASE_URL and {prefix}_API_KEY for the {name} endpoint.")
        return cls(name=name, base_url=base_url, api_key=api_key,
                   ca_cert=os.environ.get(f"{prefix}_CA_CERT"),
                   client_cert=os.environ.get(f"{prefix}_CLIENT_CERT"),
                   client_key=os.environ.get(f"{prefix}_CLIENT_KEY"))

    @property
    def host(self) -> str:
        return urlparse(self.base_url).netloc or self.base_url

    @property
    def tls_label(self) -> str:
        label = f"custom CA: {Path(self.ca_cert).name}" if self.ca_cert else "default CA bundle"
        return label + (", client certificate presented" if self.client_cert else "")


def make_client(ep: Endpoint) -> OpenAI:
    """OpenAI-compatible client that trusts the endpoint's CA (and presents a client cert if given)."""
    http_client = None
    if ep.ca_cert or ep.client_cert:
        for label, path in (("CA certificate", ep.ca_cert), ("client certificate", ep.client_cert),
                            ("client key", ep.client_key)):
            if path and not Path(path).is_file():
                sys.exit(f"{ep.name}: {label} not found: {path}")
        ctx = ssl.create_default_context(cafile=ep.ca_cert) if ep.ca_cert else ssl.create_default_context()
        # Python 3.13+ rejects CA certificates that miss some X.509 extensions.
        # Many private CAs do. Set CA_RELAX_STRICT=1 only if you hit that error.
        if os.environ.get("CA_RELAX_STRICT") == "1" and hasattr(ssl, "VERIFY_X509_STRICT"):
            ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        if ep.client_cert:
            ctx.load_cert_chain(certfile=ep.client_cert, keyfile=ep.client_key or None)
        # DefaultHttpxClient keeps the openai library's defaults (timeouts, limits)
        # and works whichever HTTP package the installed openai version uses.
        http_client = DefaultHttpxClient(verify=ctx)
    return OpenAI(base_url=ep.base_url, api_key=ep.api_key, max_retries=3, http_client=http_client)


# ----------------------------------------------------------------- helpers
RESULTS: list[dict] = []        # one row per check, for the summary table
USAGE: list[dict] = []          # token usage per call, for the quota log


def record(check: str, status: str, detail: str, raw: str = "", ms: float | None = None) -> None:
    RESULTS.append({"check": check, "status": status, "detail": detail, "raw": raw, "ms": ms})
    print(f"{check}: {status} -> {detail}")


def status_of(check: str) -> str | None:
    return next((r["status"] for r in RESULTS if r["check"] == check), None)


def detail_of(check: str) -> str:
    return next((r["detail"] for r in RESULTS if r["check"] == check), "")


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, (time.perf_counter() - t0) * 1000


def log_usage(label: str, resp) -> None:
    u = getattr(resp, "usage", None)
    if u is not None:
        USAGE.append({"call": label,
                      "prompt_tokens": getattr(u, "prompt_tokens", None),
                      "completion_tokens": getattr(u, "completion_tokens", None),
                      "total_tokens": getattr(u, "total_tokens", None)})


def short(e: Exception, limit: int = 300) -> str:
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= limit else s[:limit] + "…"


def tls_hint(e: Exception, prefix: str) -> str:
    """Turn a buried SSL error into an actionable hint."""
    chain, cur = [], e
    while cur is not None and len(chain) < 5:
        chain.append(str(cur))
        cur = cur.__cause__ or cur.__context__
    text = " ".join(chain).lower()
    if "key usage extension" in text or "basic constraints" in text:
        return " | the CA file loads but Python's strict check rejects it: re-run with CA_RELAX_STRICT=1"
    if "certificate_verify_failed" in text or "certificate verify failed" in text:
        return f" | TLS certificate not trusted: set {prefix}_CA_CERT to this endpoint's CA file"
    if "401" in text or "unauthorized" in text or "invalid api key" in text:
        return f" | key rejected: check {prefix}_API_KEY"
    return ""


def md_escape(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def list_models(client: OpenAI, label: str, prefix: str) -> list[str]:
    try:
        models, ms = timed(lambda: [m.id for m in client.models.list().data])
        record(f"{label}: models", "OK", ", ".join(models) or "(none listed)", ms=ms)
        return models
    except Exception as e:
        record(f"{label}: models", "FAILED", short(e) + tls_hint(e, prefix))
        return []


# ------------------------------------------------------------- chat checks
WEATHER_TOOL = [{"type": "function", "function": {
    "name": "get_weather",
    "description": "Get current weather for a city",
    "parameters": {"type": "object",
                   "properties": {"city": {"type": "string"}},
                   "required": ["city"]}}}]


def check_tools(client: OpenAI, model: str, tries: int) -> None:
    calls_made, raw = 0, []
    for i in range(tries):
        try:
            r, ms = timed(lambda: client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "What is the weather in Pune?"}],
                tools=WEATHER_TOOL, tool_choice="auto", max_tokens=100))
            log_usage(f"tools #{i + 1}", r)
            calls = r.choices[0].message.tool_calls
            if calls:
                calls_made += 1
                raw.append(f"try {i + 1} ({ms:.0f} ms): {calls[0].function.name}({calls[0].function.arguments})")
            else:
                raw.append(f"try {i + 1} ({ms:.0f} ms): text -> {(r.choices[0].message.content or '')[:120]!r}")
        except Exception as e:
            record("chat: tools", "NOT SUPPORTED", short(e))
            return
    status = "OK" if calls_made == tries else "PARTIAL" if calls_made else "NO TOOL CALL"
    record("chat: tools", status, f"structured tool call in {calls_made}/{tries} tries", "\n".join(raw))


def check_json_schema(client: OpenAI, model: str) -> None:
    try:
        r, ms = timed(lambda: client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Name one Indian city and its state."}],
            response_format={"type": "json_schema", "json_schema": {"name": "city", "schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}, "state": {"type": "string"}},
                "required": ["city", "state"]}}},
            max_tokens=100))
        log_usage("json_schema", r)
        content = r.choices[0].message.content
        parsed = json.loads(content)
        ok = isinstance(parsed, dict) and {"city", "state"} <= parsed.keys()
        record("chat: json_schema", "OK" if ok else "SHAPE WRONG", json.dumps(parsed), content, ms)
    except Exception as e:
        record("chat: json_schema", "NOT SUPPORTED", short(e))


def check_json_object(client: OpenAI, model: str) -> None:
    try:
        r, ms = timed(lambda: client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply in JSON with keys city and state for one Indian city."}],
            response_format={"type": "json_object"}, max_tokens=100))
        log_usage("json_object", r)
        content = r.choices[0].message.content
        record("chat: json_object", "OK", json.dumps(json.loads(content)), content, ms)
    except Exception as e:
        record("chat: json_object", "NOT SUPPORTED", short(e))


def check_usage(client: OpenAI, model: str) -> None:
    try:
        r, ms = timed(lambda: client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": "Say OK."}], max_tokens=5))
        log_usage("usage", r)
        u = r.usage
        if u is not None and getattr(u, "total_tokens", None) is not None:
            record("chat: usage reported", "OK",
                   f"prompt={u.prompt_tokens}, completion={u.completion_tokens}, total={u.total_tokens}", ms=ms)
        else:
            record("chat: usage reported", "MISSING", "response has no usage field", ms=ms)
    except Exception as e:
        record("chat: usage reported", "FAILED", short(e))


def run_chat_checks(ep: Endpoint, tool_tries: int) -> str:
    record("chat: TLS", "INFO", ep.tls_label)
    client = make_client(ep)
    models = list_models(client, "chat", "CHAT")
    model = os.environ.get("CHAT_MODEL") or (models[0] if models else "")
    if not model:
        record("chat: model used", "FAILED", "no model listed; set CHAT_MODEL and re-run")
        return ""
    record("chat: model used", "INFO", model)
    check_tools(client, model, tool_tries)
    check_json_schema(client, model)
    check_json_object(client, model)
    check_usage(client, model)
    return model


# ------------------------------------------------------- embeddings checks
def run_embedding_checks(ep: Endpoint) -> str:
    record("embeddings: TLS", "INFO", ep.tls_label)
    client = make_client(ep)
    models = list_models(client, "embeddings", "EMBED")
    if status_of("embeddings: models") == "FAILED" and not os.environ.get("EMBED_MODEL"):
        # Some embedding servers don't implement /models; the real test is below.
        record("embeddings: note", "INFO", "model list unavailable; set EMBED_MODEL if the call below fails")
    emb_like = [m for m in models if "embed" in m.lower()]
    emb_model = os.environ.get("EMBED_MODEL") or (emb_like or models or [""])[0]
    if not emb_model:
        record("embeddings", "FAILED", "no model name; set EMBED_MODEL and re-run")
        return ""
    try:
        e, ms = timed(lambda: client.embeddings.create(model=emb_model, input=["hello world", "customs allowance"]))
        dims = {len(d.embedding) for d in e.data}
        record("embeddings", "OK", f"model={emb_model}, dimension={dims.pop() if len(dims) == 1 else sorted(dims)}", ms=ms)
        u = getattr(e, "usage", None)
        if u is not None:
            USAGE.append({"call": "embeddings", "prompt_tokens": getattr(u, "prompt_tokens", None),
                          "completion_tokens": 0, "total_tokens": getattr(u, "total_tokens", None)})
    except Exception as ex:
        record("embeddings", "FAILED", f"model={emb_model}: {short(ex)}{tls_hint(ex, 'EMBED')}")
    return emb_model


# ------------------------------------------------------------ next steps
def next_steps(chat_model: str) -> list[str]:
    steps = []
    if chat_model:
        steps.append(f"Develop locally on the same model family as `{chat_model}` (Ollama or vLLM) and write the name in `../docs/SPEC.md`.")

    t = status_of("chat: tools")
    if t == "OK":
        steps.append("Tools: native tool calling works. Use the `tools` parameter in the planner; still validate arguments with Pydantic.")
    elif t == "PARTIAL":
        steps.append("Tools: tool calls are unreliable. Use native tools with a fallback: if no tool call comes back, re-ask for the call as JSON text and parse it. Log the rate in COMPENSATIONS.md.")
    elif t is not None:
        steps.append('Tools: treat as unsupported. Ask for tool calls as JSON text (`{"tool": ..., "args": ...}`), parse and validate with Pydantic, retry up to 2 times. Tell the mentor.')

    if status_of("chat: json_schema") == "OK":
        steps.append("JSON: constrained decoding works. Use `json_schema` for planner, writer and verifier outputs; record \"with vs. without\" as an experiment.")
    elif status_of("chat: json_object") == "OK":
        steps.append("JSON: only `json_object` works. Valid JSON is guaranteed but not the shape: use JSON mode plus Pydantic validation and retries.")
    elif status_of("chat: json_object") is not None:
        steps.append("JSON: no guarantees. Use few-shot JSON examples, Pydantic validation and retry with the error message (the `instructor` library automates this).")

    if status_of("embeddings") == "OK":
        d = detail_of("embeddings")
        steps.append(f"Embeddings: configure the vector store with {d.split('dimension=')[-1]} dimensions ({d.split(',')[0]}).")
    elif status_of("embeddings") is not None:
        steps.append("Embeddings: not confirmed. Check the EMBED_* settings (the hint in the summary says which), or use `bge-small-en-v1.5` locally for now.")

    u = status_of("chat: usage reported")
    if u == "OK":
        steps.append("Usage: log `prompt_tokens` and `completion_tokens` per call in `src/llm.py` for the cost metric and quota log.")
    elif u is not None:
        steps.append("Usage: not reported. Count tokens client-side (tokenizer of the same model family) for the cost metric.")

    steps.append("`src/llm.py`: keep two clients built with `Endpoint` + `make_client()` from this script: one for chat, one for embeddings, each with its own key and certificate.")
    steps.append("Copy every finding into `../docs/COMPENSATIONS.md`; they feed the graded section \"What did we do to compensate for a small model?\".")
    return steps


# ----------------------------------------------------------------- report
def write_report(path: Path, chat: Endpoint | None, emb: Endpoint | None,
                 chat_model: str, emb_model: str, started: dt.datetime) -> None:
    lines = ["# Endpoint capability check", "",
             f"- **Run at:** {started.strftime('%Y-%m-%d %H:%M %Z')}",
             f"- **openai library:** {__import__('openai').__version__}", "",
             "| Endpoint | Host | Model | TLS |", "| --- | --- | --- | --- |"]
    if chat:
        lines.append(f"| Chat (LLM) | `{chat.host}` | `{chat_model or '-'}` | {chat.tls_label} |")
    if emb:
        lines.append(f"| Embeddings | `{emb.host}` | `{emb_model or '-'}` | {emb.tls_label} |")

    lines += ["", "## Summary", "", "| Check | Result | Detail | Latency |", "| --- | --- | --- | --- |"]
    for r in RESULTS:
        ms = f"{r['ms']:.0f} ms" if r["ms"] is not None else ""
        lines.append(f"| {r['check']} | **{r['status']}** | {md_escape(r['detail'])} | {ms} |")

    lines += ["", "## What to do next", ""]
    lines += [f"{i}. {s}" for i, s in enumerate(next_steps(chat_model), 1)]

    if USAGE:
        total = sum(u["total_tokens"] or 0 for u in USAGE)
        lines += ["", "## Token usage (for the quota log)", "",
                  "| Call | Prompt | Completion | Total |", "| --- | --- | --- | --- |"]
        for u in USAGE:
            lines.append(f"| {u['call']} | {u['prompt_tokens']} | {u['completion_tokens']} | {u['total_tokens']} |")
        lines.append(f"| **All calls** | | | **{total}** |")

    raws = [r for r in RESULTS if r["raw"]]
    if raws:
        lines += ["", "## Raw responses", ""]
        for r in raws:
            lines += [f"<details><summary>{r['check']}</summary>", "", "```", r["raw"], "```", "", "</details>", ""]

    lines += ["", "## Still to confirm with the programme office", "",
              "- Per-team token quota and price per million tokens, for chat and for embeddings (cost metric).",
              "- Rate limits (requests and tokens per minute) for each endpoint.",
              "- Chat context length (expected 8,192 tokens per call, 1,024 max output) and the embeddings input limit."]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport written to {path}")


# ------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="docs/endpoint_check.md")
    ap.add_argument("--tool-tries", type=int, default=3,
                    help="how many times to try the tool call (the guide suggests 3-5)")
    ap.add_argument("--only", choices=["chat", "embeddings"], help="check just one endpoint")
    args = ap.parse_args()

    started = dt.datetime.now().astimezone()
    chat = Endpoint.from_env("chat", "CHAT") if args.only != "embeddings" else None
    emb = Endpoint.from_env("embeddings", "EMBED") if args.only != "chat" else None

    chat_model = run_chat_checks(chat, args.tool_tries) if chat else ""
    emb_model = run_embedding_checks(emb) if emb else ""

    write_report(Path(args.out), chat, emb, chat_model, emb_model, started)


if __name__ == "__main__":
    main()