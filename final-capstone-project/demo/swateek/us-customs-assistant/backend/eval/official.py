"""Official runs (plan step 13, §10.4): the frozen agent on the frozen eval set.

    uv run python -m eval.official --dry-run            # pre-flight + exact plan; sends nothing
    uv run python -m eval.official --who swateek        # run everything still to do (upgrad!)
    uv run python -m eval.official --who swateek --only planner-1 planner-1-corr

Runs: 3x planner (each with the corrections suite), 1x router, 1x tool_calling, 1x single_rag,
cache off, one request at a time. Each run is an eval.run_agent run (resumable per scenario).
Pre-flight refuses to start unless eval-v1 and the agent freeze both verify, and records the
versions and commit in docs/results/runs/official.yaml. Report: eval.eval_report.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import UTC, datetime

import yaml

from customs.config import PROJECT_ROOT, get_settings
from eval import run_agent as ra

RUNS = [
    ("planner-1", "frozen", "planner"),
    ("planner-1-corr", "corrections", "planner"),
    ("planner-2", "frozen", "planner"),
    ("planner-2-corr", "corrections", "planner"),
    ("planner-3", "frozen", "planner"),
    ("planner-3-corr", "corrections", "planner"),
    ("router", "frozen", "router"),
    ("tool_calling", "frozen", "tool_calling"),
    ("single_rag", "frozen", "single_rag"),
]
MANIFEST = ra.RUNS / "official.yaml"


def preflight() -> dict:
    """Both freezes must verify; returns what the runs are pinned to."""
    from eval.freeze_agent import LOCK as AGENT_LOCK
    from eval.freeze_agent import frozen_files, sha

    problems = []
    agent = yaml.safe_load(AGENT_LOCK.read_text(encoding="utf-8"))
    changed = [rel for rel, d in agent["files"].items() if sha(rel) != d]
    added = sorted(set(frozen_files()) - set(agent["files"]))
    if changed or added:
        problems.append(
            f"agent freeze v{agent['version']} broken: changed {changed}, added {added}"
        )
    ev_lock = PROJECT_ROOT / "pack" / "eval" / "freeze.lock.yaml"
    ev = yaml.safe_load(ev_lock.read_text(encoding="utf-8"))
    import hashlib

    bad = [rel for rel, d in ev["files"].items()
           if hashlib.sha256((ev_lock.parent / rel).read_bytes()).hexdigest() != d]  # fmt: skip
    if bad:
        problems.append(f"eval-v{ev['version']} broken: {bad}")
    s = get_settings()
    if s.agent_token_limit != 12000 or s.agent_step_limit != 10 or s.agent_tool_limit != 10:
        problems.append("caps differ from the plan (12,000 tokens, 10 model calls, 10 tool calls)")
    if problems:
        sys.exit("PRE-FLIGHT FAILED\n" + "\n".join(problems))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], check=True,
                            capture_output=True, text=True, cwd=PROJECT_ROOT).stdout.strip()  # fmt: skip
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "backend/src", "pack"],
                           check=True, capture_output=True, text=True, cwd=PROJECT_ROOT).stdout  # fmt: skip
    return {"agent_freeze": agent["version"], "eval_version": ev["version"], "commit": commit,
            "uncommitted_code_or_pack": bool(dirty.strip()), "model": s.upgrad_chat_base_url and
            "Qwen/Qwen3-8B", "caps": {"tokens": 12000, "model_calls": 10, "tool_calls": 10}}  # fmt: skip


def plan(only: list[str] | None) -> list[dict]:
    out = []
    for name, set_name, mode in RUNS:
        if only and name not in only:
            continue
        rows = ra.load(set_name)
        todo = [r for r in rows if r["id"] not in ra.done_ids(name)]
        chat, emb, cap = ra.expected_calls(todo, mode)
        out.append({"run": name, "set": set_name, "mode": mode, "scenarios": len(rows),
                    "todo": len(todo), "turns": sum(len(r["turns"]) for r in todo),
                    "chat": chat, "embed": emb, "cap": cap})  # fmt: skip
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--who")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    pins = preflight()
    print(f"pre-flight ok: agent freeze v{pins['agent_freeze']}, eval-v{pins['eval_version']}, "
          f"commit {pins['commit']}{' (+ uncommitted changes!)' if pins['uncommitted_code_or_pack'] else ''}")  # fmt: skip
    p = plan(a.only)
    print(
        f"{'run':16s} {'set':12s} {'mode':13s} {'todo':>5s} {'turns':>6s} {'chat~':>6s} {'embed~':>7s} {'cap':>5s}"
    )
    for x in p:
        print(f"{x['run']:16s} {x['set']:12s} {x['mode']:13s} {x['todo']:5d} {x['turns']:6d} "
              f"{x['chat']:6d} {x['embed']:7d} {x['cap']:5d}")  # fmt: skip
    tot = {k: sum(x[k] for x in p) for k in ("turns", "chat", "embed", "cap")}
    print(f"TOTAL: {tot['turns']} turns; expected ~{tot['chat']} chat calls + ~{tot['embed']} "
          f"embedding requests (normal paths; retries/rewrites add some); hard cap {tot['cap']}")  # fmt: skip
    if a.dry_run:
        print("dry run: nothing sent")
        return
    if not a.who:
        sys.exit("FAIL calling upgrad needs --who (quota log)")
    from langgraph.checkpoint.memory import InMemorySaver

    from customs.agent.graph import CustomsAgent

    s = get_settings().model_copy(update={"answer_cache_enabled": False})
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    manifest = yaml.safe_load(MANIFEST.read_text()) if MANIFEST.exists() else {"runs": {}}
    manifest["pins"] = pins
    # one search for all runs: embedded Qdrant allows one client per storage folder (a second
    # agent's search crashed the first resume); state stays fresh per run via the checkpointer
    from customs.retrieval.service import RegulationSearch

    search = RegulationSearch(s)
    for x in p:
        if x["todo"] == 0:
            continue
        agent = CustomsAgent(s, checkpointer=InMemorySaver(), search=search)  # fresh state per run
        t0 = time.time()
        print(f"\n=== {x['run']} ({x['set']}, {x['mode']}): {x['todo']} scenarios", flush=True)
        totals = ra.run(x["run"], x["set"], x["mode"], [r for r in ra.load(x["set"])
                        if r["id"] not in ra.done_ids(x["run"])], agent, a.who)  # fmt: skip
        ra.report(x["run"])
        manifest["runs"][x["run"]] = {"set": x["set"], "mode": x["mode"], **totals,
                                      "minutes": round((time.time() - t0) / 60, 1),
                                      "finished": datetime.now(UTC).isoformat(timespec="seconds"),
                                      "agent_freeze": pins["agent_freeze"]}  # fmt: skip
        MANIFEST.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    print("\nall runs done; next: uv run python -m eval.eval_report")


if __name__ == "__main__":
    main()
