"""Day 9 freeze: the prompts, the retrieval settings and the budget the official runs must use.

    uv run python eval/freeze.py            # compare the code with eval/freeze.json (exit 1 if it drifted)
    uv run python eval/freeze.py --write    # record the freeze (once, after the Day 9 dry run)

eval/freeze.json holds a short hash of every prompt the model sees, and the retrieval and
budget values themselves. `run_agent.py --set eval` refuses to start if the code no longer
matches it, and every run summary records whether it did. Changing a prompt after the freeze
means writing a new freeze and saying so in WORKLOG.md: it is a visible decision, not drift.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FROZEN = ROOT / "eval" / "freeze.json"
FROZEN_KEYS = (
    "prompts",
    "retrieval",
    "budget",
)  # compared; "corpus" only when both have it


def _h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def current() -> dict:
    import importlib

    from src.agent import pipeline, planner, prompts, router, session
    from src.retrieval import retriever

    sr = importlib.import_module(
        "src.tools.search_regulations"
    )  # the module, not the tool

    reranker = os.environ.get("RERANKER", sr.DEFAULT_RERANKER)
    state = {
        "prompts": {
            "intake": _h(prompts.INTAKE),
            "writer": _h(prompts.WRITER),
            "verify_evasion": _h(prompts.VERIFY_EVASION),
            "planner": _h(planner.PLANNER),
            "turn_intake": _h(session.TURN_INTAKE),
        },
        "retrieval": {
            "method": "hybrid BM25 + dense, RRF, cross-encoder rerank",
            "reranker": reranker,
            "rrf_k": retriever.RRF_K,
            "candidates_per_retriever": retriever.CANDIDATES,
            "rerank_pool": retriever.RERANK_POOL,
            "max_k": sr.MAX_K,
            "not_citable": sorted(sr.NOT_CITABLE),
            "citations_per_rule": router.PER_RULE,
            "chunk_max_tokens": 350,  # data/rag-corpus/chunk_corpus.py default, docs/RETRIEVAL.md
        },
        "budget": {
            "max_tool_steps": pipeline.MAX_TOOL_STEPS,
            "max_tokens_per_question": pipeline.MAX_TOKENS,
            "max_plan_steps": planner.MAX_STEPS,
        },
    }
    meta = ROOT / "data" / "rag-corpus" / "index" / "meta.json"
    if meta.exists():  # git-ignored: present on a machine that built the index
        m = json.loads(meta.read_text())
        state["corpus"] = {
            k: m.get(k)
            for k in ("fingerprint", "embed_model", "n_chunks", "dim")
            if k in m
        }
    return state


def diff(frozen: dict, now: dict) -> list[str]:
    out: list[str] = []
    keys = list(FROZEN_KEYS)
    if "corpus" in frozen and "corpus" in now:
        keys.append("corpus")
    for k in keys:
        a, b = frozen.get(k) or {}, now.get(k) or {}
        for f in sorted(set(a) | set(b)):
            if a.get(f) != b.get(f):
                out.append(f"{k}.{f}: frozen {a.get(f)!r} / now {b.get(f)!r}")
    return out


def status() -> dict:
    """For run summaries: is there a freeze, and does the code match it?"""
    if not FROZEN.exists():
        return {"frozen": False}
    frozen = json.loads(FROZEN.read_text())
    d = diff(frozen, current())
    return {"frozen": True, "at": frozen.get("frozen_at"), "matches": not d, "drift": d}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true", help="record the freeze")
    ap.add_argument(
        "--note", default="", help="why (with --write): e.g. 'Day 9 checkpoint'"
    )
    args = ap.parse_args()
    now = current()
    if args.write:
        now = {
            "frozen_at": dt.datetime.now(dt.UTC).date().isoformat(),
            "note": args.note,
            **now,
        }
        FROZEN.write_text(json.dumps(now, indent=1) + "\n")
        print(f"wrote {FROZEN.relative_to(ROOT)}")
        if "corpus" not in now:
            print(
                "note: no saved index here, so the corpus fingerprint is not recorded"
            )
        return 0
    if not FROZEN.exists():
        print("no freeze yet: run with --write after the Day 9 dry run")
        return 1
    d = diff(json.loads(FROZEN.read_text()), now)
    if not d:
        print("matches the freeze")
        return 0
    print(f"DRIFT from the freeze ({len(d)}):")
    for line in d:
        print(f"  {line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
