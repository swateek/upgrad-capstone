"""Attach the plan §8 scores to the official runs' Langfuse traces, from the run records.

    uv run python -m eval.langfuse_scores --dry-run     # counts only; sends nothing
    uv run python -m eval.langfuse_scores               # writes the scores (Langfuse only)

The frozen agent records only `outcome` on its traces. Everything else the plan asks for per
answer is in docs/results/runs/<run>/raw.jsonl, so it is attached here afterwards, by trace id:
`correct`, `dollar_ok`, `citation_ok` (eval), `verifier_passed`, `revisions`, `plan_fallback`,
`retrieval_miss_recovered`, `model_calls`, `tool_calls`. Score ids are fixed per trace and
name, so a rerun overwrites instead of duplicating. Sends nothing to upgrad.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter

from customs.config import get_settings
from eval import run_agent as ra
from eval.official import RUNS


def trace_id(card: dict) -> str | None:
    url = card.get("meta", {}).get("trace_url") or ""
    return url.rstrip("/").split("/")[-1] or None


def scores_for(run: str, mode: str, t: dict) -> list[tuple[str, float, str]]:
    """(name, value, data type) for one turn."""
    card, sc = t["card"], t["score"]
    m = card.get("meta", {})
    events = [e["event"] for e in m.get("events", [])]
    out = [("correct", float(t["correct"]), "BOOLEAN"),
           ("model_calls", float(m.get("model_calls", 0)), "NUMERIC"),
           ("tool_calls", float(m.get("tool_calls", 0)), "NUMERIC")]  # fmt: skip
    if sc.get("owe_ok") is not None:
        out.append(("dollar_ok", float(sc["owe_ok"]), "BOOLEAN"))
    if sc.get("cite_ok") is not None:
        out.append(("citation_ok", float(sc["cite_ok"]), "BOOLEAN"))
    reached_verifier = card["outcome"] == "answered" or m.get("escalation") == "verifier_failed"
    if reached_verifier and mode != "single_rag":
        out.append(("verifier_passed", float(m.get("escalation") != "verifier_failed"), "BOOLEAN"))
        out.append(("revisions", float(events.count("verifier_failed") > 0), "NUMERIC"))
        out.append(("retrieval_miss_recovered",
                    float(len(m.get("retrieval_miss_recovered") or [])), "NUMERIC"))  # fmt: skip
    if m.get("plan_source"):
        out.append(("plan_fallback", float(m["plan_source"] == "fallback"), "BOOLEAN"))
    return out


def collect() -> tuple[list[dict], Counter]:
    rows, missing = [], Counter()
    for run, _set, mode in RUNS:
        for rec in _raw(run):
            for t in rec["turns"]:
                tid = trace_id(t["card"])
                if not tid:
                    missing[run] += 1
                    continue
                for name, value, dtype in scores_for(run, mode, t):
                    sid = hashlib.sha256(f"{tid}:{name}".encode()).hexdigest()[:32]
                    rows.append({"id": sid, "trace_id": tid, "name": name, "value": value,
                                 "data_type": dtype, "run": run})  # fmt: skip
    return rows, missing


def _raw(run: str) -> list[dict]:
    path = ra.RUNS / run / "raw.jsonl"
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    rows, missing = collect()
    by_name = Counter(r["name"] for r in rows)
    traces = len({r["trace_id"] for r in rows})
    print(f"{len(rows)} scores on {traces} traces: {dict(by_name)}")
    if missing:
        print(f"turns without a trace: {dict(missing)}")
    if a.dry_run:
        print("dry run: nothing sent")
        return
    from langfuse import Langfuse

    s = get_settings()
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        raise SystemExit("FAIL Langfuse keys not set")
    lf = Langfuse(public_key=s.langfuse_public_key,
                  secret_key=s.langfuse_secret_key.get_secret_value(),
                  base_url=s.langfuse_base_url)  # fmt: skip
    for r in rows:
        lf.create_score(score_id=r["id"], trace_id=r["trace_id"], name=r["name"],
                        value=r["value"], data_type=r["data_type"],
                        environment=s.trace_environment,
                        metadata={"run": r["run"], "source": "eval.langfuse_scores"})  # fmt: skip
    lf.flush()
    print(f"sent {len(rows)} scores")


if __name__ == "__main__":
    main()
