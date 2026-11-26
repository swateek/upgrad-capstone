"""Build eval/redteam.jsonl from eval/redteam.yaml.

Refusal items keep their own gold; items that must still be answered copy the gold (and facts) of
their `source` dev item, as the paraphrase set does, so no new gold is calculated.

    uv run python eval/build_redteam.py
    uv run python eval/run_agent.py --set redteam --run-name redteam-day8
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SOURCE, OUT, DEV = HERE / "redteam.yaml", HERE / "redteam.jsonl", HERE / "dev_set.jsonl"


def build(source: Path = SOURCE, dev_path: Path = DEV) -> list[dict]:
    dev = {
        d["id"]: d
        for d in (json.loads(x) for x in dev_path.read_text().splitlines() if x.strip())
    }
    out, seen = [], set()
    for it in yaml.safe_load(source.read_text())["items"]:
        if it["id"] in seen:
            raise ValueError(f"duplicate id {it['id']}")
        seen.add(it["id"])
        if "source" in it:
            if it["source"] not in dev:
                raise ValueError(f"{it['id']}: unknown source {it['source']}")
            d = dev[it["source"]]
            gold = {
                **d["gold"],
                "must_not_contain": list(d["gold"].get("must_not_contain", []))
                + it.get("must_not_contain", []),
            }
            facts = d["facts"]
        else:
            if "gold" not in it:
                raise ValueError(f"{it['id']}: needs gold or a source")
            gold = {
                "outcome": it["gold"]["outcome"],
                "reason": it["gold"].get("reason"),
                "bottom_line": [],
                "citations": [],
                "must_not_contain": it.get("must_not_contain", []),
            }
            facts = None
        out.append(
            {
                "id": it["id"],
                "set": "redteam",
                "type": it["category"],
                "source": it.get("source"),
                "question": it["question"],
                "facts": facts,
                "inject_into_retrieval": it.get("inject"),
                "gold": gold,
            }
        )
    return out


def main() -> int:
    items = build()
    OUT.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items))
    print(f"wrote {OUT.name}: {len(items)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
