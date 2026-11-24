"""Merge the scenarios (pack/eval/src/*.yaml) with the independent gold (pack/eval/gold/gold.jsonl)
into the files the runners read, and optionally freeze them.

    uv run python -m eval.build_eval_sets                    # write the jsonl files, check them
    uv run python -m eval.build_eval_sets --freeze 1         # also write freeze.lock.yaml (v1)

Writes pack/eval/queries.jsonl (80), corrections.jsonl (6), dev.jsonl (20) and
retrieval_labels.jsonl (per question: the acceptable clause ids for each gold claim).

Freeze only after the user's hand-check of the 20 marked gold entries (plan step 5). The lock
covers the frozen sets, their gold and the signed-off rule tables the gold depends on; any later
change fails tests/test_eval_freeze.py until the version is bumped with a written reason in
docs/results/eval-freeze.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

from customs.config import PROJECT_ROOT

EVAL = PROJECT_ROOT / "pack" / "eval"
RULES = PROJECT_ROOT / "pack" / "rules"
SETS = {"frozen": "queries.jsonl", "corrections": "corrections.jsonl", "dev": "dev.jsonl"}
OUTCOMES = {"answered", "clarify", "refused", "out_of_scope", "escalated"}
FROZEN_FILES = [
    "queries.jsonl",
    "corrections.jsonl",
    "retrieval_labels.jsonl",
    "src/frozen.yaml",
    "src/corrections.yaml",
    "gold/gold.jsonl",
]


class EvalSetError(RuntimeError):
    pass


def load_gold() -> dict[str, dict]:
    path = EVAL / "gold" / "gold.jsonl"
    if not path.exists():
        raise EvalSetError("gold/gold.jsonl missing: the independent gold has not been built yet")
    gold = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            g = json.loads(line)
            gold[g["id"]] = g
    return gold


def check(scenario: dict, gold: dict) -> list[str]:
    sid, problems = scenario["id"], []
    gturns = gold.get("turns", [])
    if len(gturns) != len(scenario["turns"]):
        problems.append(f"{sid}: {len(scenario['turns'])} turns but {len(gturns)} gold turns")
    for t in gturns:
        if t.get("outcome") not in OUTCOMES:
            problems.append(f"{sid} turn {t.get('turn')}: bad outcome {t.get('outcome')!r}")
        if t.get("outcome") == "answered" and "disclaimer" not in t.get("notes_required", []):
            problems.append(f"{sid} turn {t.get('turn')}: answered without the disclaimer note")
        if t.get("outcome") == "clarify" and not t.get("clarify_fields"):
            problems.append(f"{sid} turn {t.get('turn')}: clarify without fields")
    return problems


def build() -> dict[str, list[dict]]:
    gold = load_gold()
    out: dict[str, list[dict]] = {}
    problems: list[str] = []
    for set_name in SETS:
        rows = []
        for s in yaml.safe_load((EVAL / "src" / f"{set_name}.yaml").read_text(encoding="utf-8")):
            g = gold.get(s["id"])
            if g is None:
                problems.append(f"{s['id']}: no gold")
                continue
            problems += check(s, g)
            rows.append(
                {
                    "id": s["id"],
                    "set": set_name,
                    "category": s["category"],
                    "turns": s["turns"],
                    "facts": s["facts"],
                    "gold": g["turns"],
                    "workings": g.get("workings", ""),
                }
            )
        out[set_name] = rows
    extra = set(gold) - {r["id"] for rows in out.values() for r in rows}
    if extra:
        problems.append(f"gold for unknown ids: {sorted(extra)}")
    if problems:
        raise EvalSetError("\n".join(problems))
    return out


def retrieval_labels(sets: dict[str, list[dict]]) -> list[dict]:
    labels = []
    for set_name in ("frozen", "dev"):
        for r in sets[set_name]:
            claims = [
                {"claim": c["claim"], "acceptable": c["acceptable"]}
                for t in r["gold"]
                for c in t.get("citations", [])
            ]
            if claims:
                labels.append(
                    {
                        "id": r["id"],
                        "set": set_name,
                        "query": " ".join(r["turns"]),
                        "claims": claims,
                    }
                )
    return labels


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8",
    )


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(version: int, sets: dict[str, list[dict]]) -> Path:
    files = {rel: sha(EVAL / rel) for rel in FROZEN_FILES}
    files.update({f"../rules/{p.name}": sha(p) for p in sorted(RULES.glob("*.yaml"))})
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    lock = {
        "version": version,
        "frozen_on": datetime.now(UTC).date().isoformat(),
        "base_commit": commit,
        "queries": len(sets["frozen"]),
        "corrections": len(sets["corrections"]),
        "by_category": dict(Counter(r["category"] for r in sets["frozen"])),
        "files": files,
    }
    path = EVAL / "freeze.lock.yaml"
    header = (
        f"# Frozen eval set, version {version}. Generated by eval.build_eval_sets --freeze; do not\n"
        "# hand-edit. tests/test_eval_freeze.py fails if any listed file changes. To change gold or\n"
        "# a rule: bump the version, regenerate this file, and write the reason in\n"
        "# docs/results/eval-freeze.md.\n"
    )
    path.write_text(header + yaml.safe_dump(lock, sort_keys=False, allow_unicode=True), "utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--freeze", type=int, metavar="VERSION", help="write freeze.lock.yaml")
    args = parser.parse_args()
    try:
        sets = build()
    except EvalSetError as err:
        print(f"FAIL\n{err}", file=sys.stderr)
        sys.exit(1)
    for set_name, fname in SETS.items():
        write_jsonl(EVAL / fname, sets[set_name])
        print(f"wrote {fname}: {len(sets[set_name])}")
    labels = retrieval_labels(sets)
    write_jsonl(EVAL / "retrieval_labels.jsonl", labels)
    print(f"wrote retrieval_labels.jsonl: {len(labels)}")
    outcomes = Counter(t["outcome"] for r in sets["frozen"] for t in r["gold"])
    print(f"frozen gold outcomes per turn: {dict(outcomes)}")
    if args.freeze:
        print(f"wrote {freeze(args.freeze, sets)}")


if __name__ == "__main__":
    main()
