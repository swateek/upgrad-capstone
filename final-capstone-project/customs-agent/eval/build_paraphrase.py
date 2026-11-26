"""Build eval/paraphrase_set.jsonl from eval/paraphrase_raw.jsonl (see eval/PARAPHRASE_BRIEF.md).

Each rewording keeps the facts of one dev item, so its gold (and planted document, for injection
items) is copied from that item. Checks ids, sources, duplicates and that no question is a copy of
its source.

    uv run python eval/build_paraphrase.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

EVAL = Path(__file__).resolve().parent
RAW = EVAL / "paraphrase_raw.jsonl"
OUT = EVAL / "paraphrase_set.jsonl"
ID = re.compile(r"^P(\d{2})[a-z]$")


def build(raw_path: Path = RAW, dev_path: Path = EVAL / "dev_set.jsonl") -> list[dict]:
    dev = {
        d["id"]: d
        for d in (json.loads(x) for x in dev_path.read_text().splitlines() if x.strip())
    }
    items, seen, errors = [], set(), []
    for n, line in enumerate(raw_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            p = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"line {n}: not JSON ({e})")
            continue
        pid, src, q = (
            p.get("id", ""),
            p.get("source", ""),
            (p.get("question") or "").strip(),
        )
        m = ID.match(pid)
        if not m:
            errors.append(f"line {n}: id {pid!r} is not like P01a")
        elif f"D{m.group(1)}" != src:
            errors.append(f"line {n}: id {pid} does not match source {src}")
        if src not in dev:
            errors.append(f"line {n}: unknown source {src!r}")
            continue
        if pid in seen:
            errors.append(f"line {n}: duplicate id {pid}")
        seen.add(pid)
        if not q:
            errors.append(f"line {n}: empty question")
        elif q.lower() == dev[src]["question"].strip().lower():
            errors.append(f"line {n}: {pid} is a copy of {src}")
        d = dev[src]
        item = {
            "id": pid,
            "set": "paraphrase",
            "type": d["type"],
            "source": src,
            "changed": p.get("changed", ""),
            "question": q,
            "facts": d["facts"],
            "gold": d["gold"],
        }
        if d.get("inject_into_retrieval"):
            item["inject_into_retrieval"] = d["inject_into_retrieval"]
        items.append(item)
    if errors:
        raise ValueError("\n".join(errors))
    return items


def main() -> int:
    if not RAW.exists():
        print(f"{RAW.name} not found: write it first (eval/PARAPHRASE_BRIEF.md)")
        return 1
    try:
        items = build()
    except ValueError as e:
        print(f"not built:\n{e}")
        return 1
    OUT.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items))
    per = {}
    for i in items:
        per[i["source"]] = per.get(i["source"], 0) + 1
    thin = [s for s in sorted(per) if per[s] < 3]
    print(f"wrote {OUT.name}: {len(items)} questions from {len(per)} dev items")
    if thin:
        print(f"fewer than 3 rewordings: {', '.join(thin)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
