"""Build eval-v3 (held-out) and dev-v2 from the AI-generated scenarios (SPEC v2).

    uv run python eval/build_v3.py prepare     # generated/*.yaml -> scenarios_v3.yaml (checked, split)
    uv run python eval/build_v3.py workbook    # scenarios_v3.yaml -> gold_v3.xlsx (formulas)
    soffice --headless --convert-to xlsx --outdir /tmp eval/gold_v3.xlsx && cp /tmp/gold_v3.xlsx eval/
    uv run python eval/build_v3.py export      # -> eval_set_v3.jsonl, dev_set_v2.jsonl, gold_v3.md
    uv run python eval/build_v3.py review      # -> REVIEW_V3.md (the owner's spot check)

prepare:
  1. loads eval/generated/*.yaml (written from eval/GENERATION_PROMPT_V3.md by several AIs);
  2. applies eval/generated/corrections.yaml (dropped and fixed scenarios, each with the rule);
  3. re-checks every scenario with eval/check_v3.py and stops if any issue is left;
  4. splits each type at random (fixed seed) into eval-v3 (100) and dev-v2 (the rest), so no
     generator knew which set an item would land in;
  5. adds what the generators were told not to write: the allowance allocation per alcohol line
     (highest duty + excise per litre first, SPEC 5.4), the what-if allowance, and the
     citations, from the fixed table below (the same conventions as eval-v2's gold).
workbook / export: the eval-v2 gold machinery (eval/build_eval.py) pointed at the v3 files, so
the dollar gold is computed by the same spreadsheet formulas, never by src/tools (rule 5).
"""

from __future__ import annotations

import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_eval
import check_v3

SCENARIOS = HERE / "scenarios_v3.yaml"
CORRECTIONS = HERE / "generated" / "corrections.yaml"
EVAL_SIZE = 100
SEED = 20261123  # the day the split was made; fixed so the split can be rebuilt
SETS = {"eval3": HERE / "eval_set_v3.jsonl", "dev2": HERE / "dev_set_v2.jsonl"}
IDS = {"eval3": "E3-", "dev2": "D2-"}

MONEY = ["htsus9816.00.20", "ttb-tax-rates"]
CUBA = ["31cfr515.204", "31cfr515.585"]


def citations(s: dict) -> list[str]:
    """Regulations every answer must cite, by what the gold says applies (eval-v2 conventions)."""
    g = s["gold"]
    out, lines = g["outcome"], g.get("bottom_line") or []
    if out in ("refused", "clarify"):
        return []
    if out == "escalated":
        return {
            "over_flat_rate_band": ["htsus9816.00.20"],
            "flat_rate_used": ["htsus9816.00.20"],
        }.get(g.get("reason"), [])
    if s["type"] == "whatif":
        return ["19cfr148.33", *MONEY]
    cites: list[str] = []
    if "prohibited" in lines:
        cites += CUBA
        if all(t == "prohibited" for t in lines):
            return cites
    ex = g.get("exemption")
    if ex == "standard_800_no_tobacco_under_21":
        return cites + ["cbp-duty-info"]
    cites.append(
        "19cfr148.51" if ex in ("short_trip_200", "none_200_failed") else "19cfr148.33"
    )
    p = s.get("profile") or {}
    h = check_v3.hours(p.get("trip"))
    if (
        p.get("direct_arrival_from") == "MX"
        and (h is None or h < 48)
        and ex.startswith("standard_800")
    ):
        cites.append("19cfr148.35")
    if "owe" in lines:
        cites += MONEY
    if "declare_detention_risk" in lines:
        cites.append("cbp-duty-info")
    if "relinquish_excess" in lines:
        cites.append("26usc5754")
    return list(dict.fromkeys(cites))


def allocate(s: dict) -> None:
    """gold_exempt_l on each priced alcohol line, from the exemption the gold names."""
    g = s["gold"]
    if g["outcome"] != "answered":
        return
    basket, lines = s.get("basket") or [], g.get("bottom_line") or []
    alc = [
        i
        for i, b in enumerate(basket)
        if b["category"] == "alcohol" and lines[i] != "prohibited"
    ]
    ex = g.get("exemption")
    if ex in ("none_200_failed", "standard_800_no_alcohol_under_21"):
        for i in alc:
            basket[i]["gold_exempt_l"] = 0
        return
    if ex == "short_trip_200":
        for i in alc:
            basket[i]["gold_exempt_l"] = round(check_v3.litres(basket[i]), 3)
        return
    left = 2.0 if ex == "standard_800_beneficiary_2l" else 1.0
    for i in sorted(alc, key=lambda i: -check_v3.charge_per_l(basket[i])):
        take = min(left, check_v3.litres(basket[i]))
        basket[i]["gold_exempt_l"], left = round(take, 3), round(left - take, 6)


def whatif_allowance(s: dict) -> None:
    if s.get("whatif"):
        ex = s["gold"].get("exemption")
        s["whatif"]["allowance_l"] = (
            2.0
            if ex == "standard_800_beneficiary_2l"
            else 0.0
            if "under_21" in str(ex)
            else 1.0
        )


def split(items: list[dict]) -> None:
    """Per type, a seeded shuffle; eval-v3 gets its share of each type (largest remainder)."""
    rng = random.Random(SEED)
    by_type: dict[str, list[dict]] = defaultdict(list)
    for s in items:
        by_type[s["type"]].append(s)
    n = len(items)
    quota = {t: EVAL_SIZE * len(v) / n for t, v in by_type.items()}
    take = {t: int(q) for t, q in quota.items()}
    for t in sorted(quota, key=lambda t: quota[t] - take[t], reverse=True)[
        : EVAL_SIZE - sum(take.values())
    ]:
        take[t] += 1
    counters = {"eval3": 0, "dev2": 0}
    for t in sorted(by_type):
        group = sorted(by_type[t], key=lambda s: s["source"])
        rng.shuffle(group)
        for k, s in enumerate(group):
            s["set"] = "eval3" if k < take[t] else "dev2"
    for s in sorted(items, key=lambda s: (s["set"] != "eval3", s["type"], s["source"])):
        counters[s["set"]] += 1
        s["id"] = f"{IDS[s['set']]}{counters[s['set']]:03d}"


def prepare() -> None:
    corr = yaml.safe_load(CORRECTIONS.read_text())
    items = []
    for gen, s in check_v3.load_generated():
        sid = str(s.get("id"))
        if sid in corr["drop"]:
            continue
        if fix := corr["fix"].get(sid):
            for part in ("gold", "profile"):
                if part in fix:
                    s.setdefault(part, {}).update(fix[part])
            s["correction"] = fix["why"]
        s["source"], s["generator"] = sid, gen
        items.append(s)
    left = [
        (s["source"], r.issues)
        for s in items
        if (r := check_v3.check(s, s["generator"])).issues
    ]
    if left:
        raise SystemExit(f"issues left after corrections: {left}")
    split(items)
    for s in items:  # relabels decided after the split, so set membership does not move
        if new_type := (corr["fix"].get(s["source"]) or {}).get("type_after_split"):
            s["type"] = new_type
    for s in items:
        allocate(s)
        whatif_allowance(s)
        s["gold"]["citations"] = citations(s)
    order = (
        "id",
        "set",
        "type",
        "source",
        "generator",
        "correction",
        "question",
        "profile",
        "basket",
        "whatif",
        "inject_into_retrieval",
        "gold",
    )
    items = [
        {k: s[k] for k in order if k in s} for s in sorted(items, key=lambda s: s["id"])
    ]
    header = (
        "# eval-v3 (held-out) and dev-v2, SPEC v2. Generated by eval/build_v3.py prepare from\n"
        "# eval/generated/*.yaml (AI-written from eval/GENERATION_PROMPT_V3.md) and\n"
        "# eval/generated/corrections.yaml. Do not edit by hand: change a correction and rebuild.\n"
        "# Dollar gold: eval/gold_v3.xlsx (formulas). Allocation and citations: build_v3.py rules.\n\n"
    )
    SCENARIOS.write_text(
        header
        + yaml.safe_dump(
            {"scenarios": items}, sort_keys=False, allow_unicode=True, width=200
        )
    )
    c = Counter((s["set"], s["type"]) for s in items)
    for st in ("eval3", "dev2"):
        n = sum(v for (a, _), v in c.items() if a == st)
        print(
            f"{st}: {n} scenarios  "
            + ", ".join(f"{t} {v}" for (a, t), v in sorted(c.items()) if a == st)
        )
    print(
        f"wrote {SCENARIOS.name}; generators: {dict(Counter(s['generator'] for s in items))}"
    )


# The 15 eval-v3 scenarios drawn for the owner's spot check on 2026-11-23 (one per type, seed
# 20261124, from those not corrected). Kept fixed so later corrections do not redraw the sample.
REVIEW_SAMPLE = [
    "E3-002",
    "E3-018",
    "E3-023",
    "E3-033",
    "E3-041",
    "E3-050",
    "E3-054",
    "E3-057",
    "E3-068",
    "E3-074",
    "E3-075",
    "E3-077",
    "E3-081",
    "E3-095",
    "E3-097",
]


def review() -> None:
    """eval/REVIEW_V3.md: the fixed random sample, then every corrected scenario."""
    import json

    sc = {s["id"]: s for s in yaml.safe_load(SCENARIOS.read_text())["scenarios"]}
    recs = {}
    for path in SETS.values():
        for line in path.open():
            r = json.loads(line)
            recs[r["id"]] = r

    def fmt(i: str) -> str:
        r, s = recs[i], sc[i]
        g = r["gold"]
        out = [
            f"### {i} ({r['type']}, from {s['generator']})",
            "",
            f"> {r['question']}",
            "",
        ]
        prof = {
            k: v
            for k, v in ((r.get("facts") or {}).get("profile") or {}).items()
            if v is not None
        }
        if prof:
            out.append(f"- **Facts:** {prof}")
        for n, b in enumerate(s.get("basket") or [], 1):
            q = b.get("quantity") or {}
            extra = ", ".join(
                f"{k} {b[k]}"
                for k in (
                    "unit_ml",
                    "count",
                    "abv",
                    "unit_price_usd",
                    "origin",
                    "bought_where",
                    "excise_class",
                    "gold_exempt_l",
                    "export_labelled_us",
                )
                if b.get(k) is not None
            )
            out.append(
                f"  - line {n}: {q.get('value')} × {q.get('unit')} {b['item']}, {extra}"
            )
        if s.get("whatif"):
            out.append(f"- **What-if facts:** {s['whatif']}")
        if inj := s.get("inject_into_retrieval"):
            out.append(
                f'- **Planted document** `{inj["doc_id"]}` (added to the search results): "{inj["text"]}"'
            )
        line = f"- **Gold:** {g['outcome']}"
        line += f" ({g['reason']})" if g.get("reason") else ""
        line += f", exemption {g['exemption']}" if g.get("exemption") else ""
        line += (
            f", bottom line {[b['type'] for b in g['bottom_line']]}"
            if g.get("bottom_line")
            else ""
        )
        line += f", asks {g['clarify_facts']}" if g.get("clarify_facts") else ""
        line += f", state flag {g['state_flag']}" if g.get("state_flag") else ""
        out.append(line)
        if g.get("total_usd") is not None:
            out.append(
                f"- **Dollars:** duty ${g['duty_usd']:.2f} + excise ${g['excise_usd']:.2f} = **${g['total_usd']:.2f}**"
            )
        if g.get("whatif"):
            out.append(
                f"- **What-if:** {g['whatif']['max_units']} units, owing ${g['whatif']['owed_usd']:.2f}"
            )
        if g.get("must_not_contain"):
            out.append(f"- **Must not say:** {g['must_not_contain']}")
        if g.get("citations"):
            out.append(f"- **Must cite:** {', '.join(g['citations'])}")
        if s.get("correction"):
            out.append(f"- **Corrected:** {s['correction']}")
        out.append("- **Your verdict:** ☐ right ☐ wrong: ______")
        return "\n".join(out) + "\n"

    corrected = sorted(i for i, s in sc.items() if s.get("correction"))
    doc = [
        "# eval-v3 spot check (owner)",
        "",
        (
            "Check each against the rules (SPEC v2: docs/SPEC.md; the rules as given to the generators: "
            "eval/GENERATION_PROMPT_V3.md), not against the agent. Tick right or wrong; for a wrong "
            "one, say what the rule gives. Then the results are recorded and `eval-v3` and `dev-v2` "
            "are tagged."
        ),
        "",
        (
            f"Part 1: {len(REVIEW_SAMPLE)} eval-v3 scenarios drawn at random, one per type. "
            f"Part 2: the {len(corrected)} corrected scenarios, so a person checks every change."
        ),
        "",
        "## Part 1: random sample",
        "",
        *[fmt(i) for i in REVIEW_SAMPLE],
        "## Part 2: corrected scenarios",
        "",
        *[fmt(i) for i in corrected],
    ]
    (HERE / "REVIEW_V3.md").write_text("\n".join(doc))
    print(
        f"wrote REVIEW_V3.md: {len(REVIEW_SAMPLE)} sampled, {len(corrected)} corrected"
    )


def point_build_eval() -> list[dict]:
    """Aim the eval-v2 gold machinery at the v3 files."""
    build_eval.SCENARIOS = SCENARIOS
    build_eval.WORKBOOK = HERE / "gold_v3.xlsx"
    build_eval.OUT = SETS
    build_eval.MARKDOWN = HERE / "gold_v3.md"
    items = yaml.safe_load(SCENARIOS.read_text())["scenarios"]
    for s in items:
        bl = s["gold"].get("bottom_line")
        if bl is not None and len(bl) != len(s.get("basket", [])):
            raise SystemExit(f"{s['id']}: bottom_line length differs from the basket")
    return items


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) == 2 else ""
    if cmd == "prepare":
        prepare()
    elif cmd == "workbook":
        build_eval.build_workbook(point_build_eval())
    elif cmd == "export":
        build_eval.export(point_build_eval())
    elif cmd == "review":
        review()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
