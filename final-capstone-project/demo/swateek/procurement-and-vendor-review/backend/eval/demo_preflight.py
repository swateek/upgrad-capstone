"""Demo preflight: run the scripted demo through the live API, check every answer, warm the cache.

Reads `domains/<domain>/demo.yaml`. Each scene is one conversation, so follow-up turns exercise
session state. Every turn goes through `POST /chat` exactly as the web UI sends it (SSE), so the
retrieval cache in Redis is warmed for the demo questions. Run it twice before presenting: the
first run warms the cache, the second shows demo-day latency.

    docker compose up -d                     # the stack must be running
    uv run python -m eval.demo_preflight     # API on localhost:$API_PORT (default 3401)
    uv run python -m eval.demo_preflight --scene withheld

Writes docs/results/demo-preflight.md. Exits 1 if a required turn fails a check.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import yaml

from copilot.config import PROJECT_ROOT, get_settings
from copilot.domains.loader import load_domain
from eval.e2e import _says_date


def chat(client: httpx.Client, api: str, thread_id: str, message: str) -> dict[str, Any]:
    """One /chat turn; returns the final event (or the error event) plus progress counts."""
    final: dict[str, Any] = {}
    progress = 0
    event = None
    with client.stream(
        "POST", f"{api}/chat", json={"thread_id": thread_id, "message": message}
    ) as resp:
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.read()[:200]!r}"}
        for line in resp.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if event == "progress":
                    progress += 1
                elif event in ("final", "error"):
                    final = data
    final["progress_events"] = progress
    return final


def check(expect: dict[str, Any], final: dict[str, Any]) -> list[str]:
    if final.get("error"):
        return [f"error: {final['error']}"]
    answer = final.get("answer") or ""
    low = answer.lower()
    problems = [f"missing '{s}'" for s in expect.get("contains", []) if s.lower() not in low]
    if expect.get("contains_any") and not any(s.lower() in low for s in expect["contains_any"]):
        problems.append(f"none of {expect['contains_any']}")
    if expect.get("date") and not _says_date(answer, expect["date"]):
        problems.append(f"snapshot date {expect['date']} not stated")
    if expect.get("refusal_rule") and expect["refusal_rule"] not in (
        final.get("refusal_rules") or []
    ):
        problems.append(f"refusal rule {expect['refusal_rule']} not matched")
    if expect.get("cited") and not final.get("citations"):
        problems.append("no citation")
    if expect.get("critic_passed") and not final.get("critic_passed"):
        problems.append("critic flagged")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--api", default=f"http://localhost:{os.environ.get('API_PORT', '3401')}")
    ap.add_argument("--scene", action="append", help="run only these scene ids")
    args = ap.parse_args()

    settings = get_settings()
    domain = load_domain(settings.domain_dir)
    script = yaml.safe_load(domain.path("demo.yaml").read_text(encoding="utf-8"))
    scenes = [s for s in script["scenes"] if not args.scene or s["id"] in args.scene]
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")

    rows, required_failures = [], 0
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
        health = client.get(f"{args.api}/health").json()
        print(f"API {args.api} · {json.dumps(health)[:240]}")
        # the provider the running API serves, not this shell's .env
        provider = health.get("provider") or settings.provider
        out = PROJECT_ROOT / "docs" / "results" / provider / "demo-preflight.md"
        for scene in scenes:
            thread_id = f"demo-{scene['id']}-{stamp}"
            print(f"\n[{scene['id']}] {scene['title']}  (thread {thread_id})")
            for turn in scene["turns"]:
                t0 = time.perf_counter()
                final = chat(client, args.api, thread_id, turn["say"])
                secs = time.perf_counter() - t0
                problems = check(turn.get("expect", {}), final)
                ok = not problems
                if not ok and not turn.get("optional"):
                    required_failures += 1
                flag = "PASS" if ok else ("WARN" if turn.get("optional") else "FAIL")
                print(f"  {flag} {secs:5.1f}s  {turn['say'][:70]}")
                for p in problems:
                    print(f"         - {p}")
                if problems:
                    answer = (final.get("answer") or "").replace("\n", " ")
                    print(f"         answer: {answer[:500]}")
                rows.append(
                    {
                        "scene": scene["id"],
                        "say": turn["say"],
                        "eval_id": turn.get("eval_id"),
                        "optional": bool(turn.get("optional")),
                        "result": flag,
                        "problems": problems,
                        "seconds": round(secs, 1),
                        "steps": final.get("steps"),
                        "tool_calls": final.get("tool_calls"),
                        "critic_passed": final.get("critic_passed"),
                        "answer": (final.get("answer") or "")[:400],
                    }
                )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report(args.api, stamp, rows, health), encoding="utf-8")
    total = sum(r["seconds"] for r in rows)
    print(
        f"\n{sum(r['result'] == 'PASS' for r in rows)}/{len(rows)} passed · "
        f"{total:.0f} s of agent time · {out.relative_to(PROJECT_ROOT)}"
    )
    return 1 if required_failures else 0


def report(api: str, stamp: str, rows: list[dict[str, Any]], health: dict[str, Any]) -> str:
    lines = [
        f"# Demo preflight ({health.get('provider', '?')})",
        "",
        (
            f"{stamp} UTC · API `{api}` · provider {health.get('provider', '?')} · chat "
            f"`{health.get('chat_model', '?')}` · embeddings "
            f"`{health.get('embedding_model', '?')}` · reranker `{health.get('reranker')}` · "
            "script `domains/<domain>/demo.yaml`"
        ),
        "",
        "| Scene | Turn | Eval id | Result | Seconds | Steps | Tools | Problems |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['scene']} | {r['say']} | {r['eval_id'] or 'follow-up'} | {r['result']} | "
            f"{r['seconds']} | {r['steps']} | {r['tool_calls']} | "
            f"{'; '.join(r['problems']) or '–'} |"
        )
    lines += [
        "",
        (
            f"Agent time for the whole script: {sum(r['seconds'] for r in rows):.0f} s. "
            "Answers are in the console output; full traces are in Langfuse (session = thread id)."
        ),
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
