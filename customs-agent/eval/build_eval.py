"""Build the gold workbook and export the evaluation sets.

The dollar gold comes from spreadsheet formulas in eval/gold.xlsx, not from src/tools
(CLAUDE.md rule 5). This script only copies inputs into the workbook and, after the
workbook has been recalculated, copies the computed values into JSONL.

    uv run python eval/build_eval.py workbook   # scenarios.yaml -> gold.xlsx (formulas, no values yet)
    # recalculate: open gold.xlsx in Excel or LibreOffice and save, or
    #   soffice --headless --convert-to xlsx --outdir /tmp eval/gold.xlsx && cp /tmp/gold.xlsx eval/
    uv run python eval/build_eval.py export     # gold.xlsx values + scenarios.yaml -> eval_set.jsonl, dev_set.jsonl, gold.md

Rates in the workbook are typed in from the official sources (TTB tax-rate table, HTSUS
9816.00.20), not read from data/rates.yaml, so a wrong number in rates.yaml is caught.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import yaml
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent
SCENARIOS = HERE / "scenarios.yaml"
WORKBOOK = HERE / "gold.xlsx"
OUT = {"eval": HERE / "eval_set.jsonl", "dev": HERE / "dev_set.jsonl"}
MARKDOWN = HERE / "gold.md"

EXPECTED_COUNTS = {
    "eval": {
        "alcohol_excess_800": 12,
        "alcohol_cbi_2L": 4,
        "exemption_200_all_or_nothing": 8,
        "tobacco_over_limit": 7,
        "cuban_origin": 6,
        "sanctions_escalate": 1,
        "under_21": 4,
        "mixed_basket": 10,
        "whatif": 4,
        "clarify": 8,
        "state_flag": 3,
        "out_of_scope": 5,
        "refuse_evasion": 4,
        "injection_doc": 2,
        "injection_user": 2,
    },
    "dev": None,  # 20 in total, any mix
}

FONT = "Arial"
BLUE = Font(name=FONT, color="0000FF")
BLACK = Font(name=FONT)
BOLD = Font(name=FONT, bold=True)
HEAD_FILL = PatternFill("solid", fgColor="DDDDDD")
INPUT_FILL = PatternFill("solid", fgColor="FFFF00")

FREE_ORIGINS = {  # HTSUS 9816.00.20 special column; country lists as in docs/SPEC.md 5.5
    "S": ["MX", "CA"],
    "P": ["CR", "DO", "SV", "GT", "HN", "NI"],
    "BH": ["BH"],
    "CL": ["CL"],
    "CO": ["CO"],
    "IL": ["IL"],
    "JO": ["JO"],
    "KR": ["KR"],
    "MA": ["MA"],
    "OM": ["OM"],
    "PA": ["PA"],
    "PE": ["PE"],
    "SG": ["SG"],
}
COLUMN2 = ["BY", "CU", "KP", "RU"]
TTB = "TTB tax rates, https://www.ttb.gov/what-we-do/taxes-and-filing/tax-rates (fetched 2026-11-21)"
HTS = "HTSUS 9816.00.20 (corpus: htsus_9816_flat_rate.md)"

LINE_HEADERS = [
    "scenario",
    "set",
    "line",
    "item",
    "excise_class",
    "origin",
    "unit_ml",
    "units",
    "abv_pct",
    "unit_price_usd",
    "exempt_l (input)",
    "total_l",
    "excess_l",
    "dutiable_value_usd",
    "duty_rate",
    "duty_usd",
    "excise_rate",
    "proof_factor",
    "excess_gallons",
    "excise_usd",
    "line_total_usd",
    "charge_per_l (check)",
    "value_unrounded_usd",
    "excise_unrounded_usd",
]
WHATIF_HEADERS = [
    "scenario",
    "units",
    "unit_ml",
    "abv_pct",
    "unit_price_usd",
    "origin",
    "excise_class",
    "allowance_l",
    "owe_less_than_usd",
    "total_l",
    "excess_l",
    "dutiable_value_usd",
    "duty_rate",
    "duty_usd",
    "excise_usd",
    "owed_usd",
    "under_target",
    "within_commercial_threshold",
    "counts",
]


def load() -> list[dict]:
    return yaml.safe_load(SCENARIOS.read_text())["scenarios"]


def check_counts(items: list[dict]) -> None:
    ids = [s["id"] for s in items]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    if dupes:
        raise SystemExit(f"duplicate ids: {dupes}")
    for set_name, expected in EXPECTED_COUNTS.items():
        got = Counter(s["type"] for s in items if s["set"] == set_name)
        if expected is not None and dict(got) != expected:
            raise SystemExit(
                f"{set_name} type counts differ: {dict(got)} vs {expected}"
            )
    if (
        sum(1 for s in items if s["set"] == "eval") != 80
        or sum(1 for s in items if s["set"] == "dev") != 20
    ):
        raise SystemExit("need 80 eval and 20 dev scenarios")
    for s in items:
        bl = s["gold"].get("bottom_line")
        if bl is not None and len(bl) != len(s.get("basket", [])):
            raise SystemExit(
                f"{s['id']}: bottom_line has {len(bl)} entries for {len(s.get('basket', []))} lines"
            )


def priced_lines(s: dict) -> list[tuple[int, dict]]:
    """Alcohol lines that get a dollar calculation: answered scenarios, not prohibited."""
    if s["gold"]["outcome"] != "answered":
        return []
    return [
        (i, ln) for i, ln in enumerate(s.get("basket", []), 1) if "gold_exempt_l" in ln
    ]


def header(ws, headers: list[str]) -> None:
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font, cell.fill = BOLD, HEAD_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions[get_column_letter(c)].width = max(10, min(22, len(h) + 2))
    ws.freeze_panes = "A2"


def rate_lookup(origin_ref: str) -> str:
    return (
        f"=IF(ISNUMBER(MATCH({origin_ref},Rates!$F$2:$F$40,0)),Rates!$B$6,"
        f"IF(ISNUMBER(MATCH({origin_ref},Rates!$H$2:$H$10,0)),Rates!$B$7,Rates!$B$5))"
    )


def excise_lookup(class_ref: str) -> str:
    return f"INDEX(Rates!$B$12:$B$16,MATCH({class_ref},Rates!$A$12:$A$16,0))"


def build_workbook(items: list[dict]) -> None:
    wb = Workbook()
    readme = wb.active
    readme.title = "README"
    notes = [
        "DeclareRight gold workbook (independent of src/tools; CLAUDE.md rule 5)",
        "",
        "Blue text on yellow = hand input (copied from eval/scenarios.yaml by build_eval.py). Black = formula.",
        "Rates: typed in from the official sources named in column D. Edit there; every formula updates.",
        "Lines: one row per priced alcohol line. exempt_l is the hand allocation: litres of that line inside",
        "  the exemption, taken from the line with the highest duty + excise per litre first (19 CFR 148.33(b)).",
        "  charge_per_l is shown so the allocation can be checked by eye.",
        "Conventions (docs/SPEC.md 5.1): dutiable value per line = unit price x excess volume / unit volume,",
        "  rounded to the dollar; duty and excise per line rounded to the cent; totals are sums of rounded lines.",
        "Whatif: one block of 12 rows per what-if scenario. under_target = owed below the target; within_commercial_threshold",
        "  = total <= 9 L and <= 12 units (docs/SPEC.md 5.4: escalate only above them). counts = both. The answer is the largest n that counts.",
        "Scenarios: totals per scenario (SUMIFS over Lines) and the what-if answers. Exported to JSONL.",
        "Solo protocol: re-check 20 scenarios by hand the next day; settle disagreements against the regulation text.",
    ]
    for r, t in enumerate(notes, 1):
        readme.cell(row=r, column=1, value=t).font = BOLD if r == 1 else BLACK
    readme.column_dimensions["A"].width = 110

    # ------------------------------------------------------------------ Rates
    rates = wb.create_sheet("Rates")
    header(rates, ["name", "value", "unit", "source"])
    rates.column_dimensions["A"].width = 26
    rates.column_dimensions["D"].width = 70
    rows = [
        (
            "liters_per_us_gallon",
            3.785411784,
            "L / gal",
            "NIST: 1 US gallon = 231 in^3 = 3.785411784 L",
        ),
        (
            "us_gallons_per_beer_barrel",
            31,
            "gal / bbl",
            "26 USC 5051: barrel of 31 gallons",
        ),
        ("beer_per_barrel", 18.00, "$ / bbl", TTB),
        ("duty_general", 0.03, "of value", f"{HTS}: 3% general"),
        (
            "duty_free_program",
            0.0,
            "of value",
            f"{HTS}: Free for listed programmes (column F)",
        ),
        ("duty_column2", 0.04, "of value", f"{HTS}: 4% column 2"),
        ("flat_rate_band_usd", 1000, "$", f"{HTS}: next $1,000 over the exemption"),
    ]
    for r, (name, value, unit, src) in enumerate(rows, 2):
        rates.cell(row=r, column=1, value=name).font = BLACK
        c = rates.cell(row=r, column=2, value=value)
        c.font, c.fill = BLUE, INPUT_FILL
        rates.cell(row=r, column=3, value=unit).font = BLACK
        rates.cell(row=r, column=4, value=src).font = BLACK
    rates.cell(row=11, column=1, value="excise_class").font = BOLD
    rates.cell(row=11, column=2, value="rate").font = BOLD
    rates.cell(row=11, column=3, value="per").font = BOLD
    excise = [
        ("wine_still_le16", 1.07, "wine gallon", TTB + ": still wine not over 16%"),
        ("wine_still_16_21", 1.57, "wine gallon", TTB + ": over 16% to 21%"),
        (
            "sparkling",
            3.40,
            "wine gallon",
            TTB + ": champagne and other sparkling wine",
        ),
        ("spirits", 13.50, "proof gallon", TTB + ": distilled spirits"),
        ("beer", "=B4/B3", "gallon", "beer_per_barrel / gallons_per_barrel"),
    ]
    for r, (name, value, per, src) in enumerate(excise, 12):
        rates.cell(row=r, column=1, value=name).font = BLACK
        c = rates.cell(row=r, column=2, value=value)
        if isinstance(value, str):
            c.font = BLACK
        else:
            c.font, c.fill = BLUE, INPUT_FILL
        c.number_format = "0.0000"
        rates.cell(row=r, column=3, value=per).font = BLACK
        rates.cell(row=r, column=4, value=src).font = BLACK
    rates.cell(row=1, column=6, value="free_origin").font = BOLD
    rates.cell(row=1, column=7, value="programme").font = BOLD
    r = 2
    for prog, countries in FREE_ORIGINS.items():
        for cc in countries:
            rates.cell(row=r, column=6, value=cc).font = BLUE
            rates.cell(row=r, column=7, value=prog).font = BLACK
            r += 1
    rates.cell(row=1, column=8, value="column2_origin").font = BOLD
    for i, cc in enumerate(COLUMN2, 2):
        rates.cell(row=i, column=8, value=cc).font = BLUE
    rates["F1"].comment = Comment(
        "Programme symbols confirmed in HTSUS General Note 3(c)(i) and the 9816.00.20 Special column (docs/SPEC.md 5.5).",
        "eval",
    )

    # ------------------------------------------------------------------ Lines
    lines = wb.create_sheet("Lines")
    header(lines, LINE_HEADERS)
    row = 2
    for s in items:
        for i, ln in priced_lines(s):
            r = row
            values = [
                s["id"],
                s["set"],
                i,
                ln["item"],
                ln["excise_class"],
                ln["origin"],
                ln["unit_ml"],
                ln["quantity"]["value"],
                ln["abv"],
                ln["unit_price_usd"],
                ln["gold_exempt_l"],
            ]
            for c, v in enumerate(values, 1):
                cell = lines.cell(row=r, column=c, value=v)
                cell.font = BLUE if c >= 5 else BLACK
                if c == 11:
                    cell.fill = INPUT_FILL
            f = {
                12: f"=G{r}*H{r}/1000",
                13: f"=ROUND(L{r}-K{r},6)",
                14: f"=ROUND(J{r}*M{r}*1000/G{r},0)",
                15: rate_lookup(f"F{r}"),
                16: f"=ROUND(N{r}*O{r},2)",
                17: "=" + excise_lookup(f"E{r}"),
                18: f'=IF(E{r}="spirits",I{r}*2/100,1)',
                19: f"=M{r}/Rates!$B$2",
                20: f"=ROUND(S{r}*Q{r}*R{r},2)",
                21: f"=P{r}+T{r}",
                22: f"=O{r}*J{r}*1000/G{r}+Q{r}*R{r}/Rates!$B$2",
                23: f"=J{r}*M{r}*1000/G{r}",
                24: f"=S{r}*Q{r}*R{r}",
            }
            fmt = {
                12: "0.000",
                13: "0.000",
                14: "$#,##0",
                15: "0%",
                16: "$#,##0.00",
                17: "0.0000",
                18: "0.00",
                19: "0.000000",
                20: "$#,##0.00",
                21: "$#,##0.00",
                22: "$#,##0.000",
                23: "$#,##0.0000",
                24: "$#,##0.0000",
            }
            for c, formula in f.items():
                cell = lines.cell(row=r, column=c, value=formula)
                cell.font, cell.number_format = BLACK, fmt[c]
            row += 1
    last_line = row - 1

    # ----------------------------------------------------------------- Whatif
    wi = wb.create_sheet("Whatif")
    header(wi, WHATIF_HEADERS)
    row = 2
    for s in items:
        w = s.get("whatif")
        if not w:
            continue
        for n in range(1, 13):
            r = row
            values = [
                s["id"],
                n,
                w["unit_ml"],
                w["abv"],
                w["unit_price_usd"],
                w["origin"],
                w["excise_class"],
                w["allowance_l"],
                w["owe_less_than_usd"],
            ]
            for c, v in enumerate(values, 1):
                wi.cell(row=r, column=c, value=v).font = BLUE if c >= 3 else BLACK
            f = {
                10: f"=B{r}*C{r}/1000",
                11: f"=MAX(0,ROUND(J{r}-H{r},6))",
                12: f"=ROUND(E{r}*K{r}*1000/C{r},0)",
                13: rate_lookup(f"F{r}"),
                14: f"=ROUND(L{r}*M{r},2)",
                15: f'=ROUND(K{r}/Rates!$B$2*{excise_lookup(f"G{r}")}*IF(G{r}="spirits",D{r}*2/100,1),2)',
                16: f"=N{r}+O{r}",
                17: f"=IF(P{r}<I{r},1,0)",
                18: f"=IF(AND(J{r}<=9,B{r}<=12),1,0)",
                19: f"=Q{r}*R{r}",
            }
            fmt = {
                10: "0.000",
                11: "0.000",
                12: "$#,##0",
                13: "0%",
                14: "$#,##0.00",
                15: "$#,##0.00",
                16: "$#,##0.00",
                17: "0",
                18: "0",
                19: "0",
            }
            for c, formula in f.items():
                cell = wi.cell(row=r, column=c, value=formula)
                cell.font, cell.number_format = BLACK, fmt[c]
            row += 1
    last_wi = max(row - 1, 2)

    # -------------------------------------------------------------- Scenarios
    sc = wb.create_sheet("Scenarios")
    heads = [
        "scenario",
        "set",
        "type",
        "outcome",
        "bottom_line",
        "exemption",
        "state_flag",
        "duty_usd",
        "excise_usd",
        "total_usd",
        "dutiable_value_usd",
        "excess_l",
        "whatif_max_units",
        "whatif_owed_usd",
        "check: value within band",
        "question",
    ]
    header(sc, heads)
    sc.column_dimensions["P"].width = 100
    L = f"Lines!$A$2:$A${last_line}"
    for r, s in enumerate(items, 2):
        g = s["gold"]
        vals = [
            s["id"],
            s["set"],
            s["type"],
            g["outcome"],
            ", ".join(g.get("bottom_line") or []),
            g.get("exemption", ""),
            g.get("state_flag", ""),
        ]
        for c, v in enumerate(vals, 1):
            sc.cell(row=r, column=c, value=v).font = BLACK
        if priced_lines(s):
            f = {
                8: f"=SUMIFS(Lines!$P$2:$P${last_line},{L},A{r})",
                9: f"=SUMIFS(Lines!$T$2:$T${last_line},{L},A{r})",
                10: f"=H{r}+I{r}",
                11: f"=SUMIFS(Lines!$N$2:$N${last_line},{L},A{r})",
                12: f"=SUMIFS(Lines!$M$2:$M${last_line},{L},A{r})",
                15: f'=IF(K{r}<=Rates!$B$8,"ok","OVER BAND")',
            }
            for c, formula in f.items():
                sc.cell(row=r, column=c, value=formula).font = BLACK
        if s.get("whatif"):
            W = f"Whatif!$A$2:$A${last_wi}"
            sc.cell(
                row=r,
                column=13,
                value=f"=_xlfn.MAXIFS(Whatif!$B$2:$B${last_wi},{W},A{r},Whatif!$S$2:$S${last_wi},1)",
            )
            sc.cell(
                row=r,
                column=14,
                value=f"=SUMIFS(Whatif!$P$2:$P${last_wi},{W},A{r},Whatif!$B$2:$B${last_wi},M{r})",
            )
        for c, fm in {
            8: "$#,##0.00",
            9: "$#,##0.00",
            10: "$#,##0.00",
            11: "$#,##0",
            12: "0.000",
            14: "$#,##0.00",
        }.items():
            sc.cell(row=r, column=c).number_format = fm
        sc.cell(row=r, column=16, value=s["question"]).font = BLACK
    wb.move_sheet("Scenarios", offset=-3)
    wb.save(WORKBOOK)
    print(
        f"wrote {WORKBOOK.name}: {last_line - 1} priced lines, {last_wi - 1} what-if rows, {len(items)} scenarios"
    )


def export(items: list[dict]) -> None:
    wb = load_workbook(WORKBOOK, data_only=True)
    lines, sc = wb["Lines"], wb["Scenarios"]
    by_line: dict[tuple[str, int], dict] = {}
    for row in lines.iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            continue
        if row[13] is None:
            raise SystemExit(
                "gold.xlsx has no computed values: recalculate it first (see module docstring)"
            )
        by_line[(row[0], row[2])] = {
            "line": row[2],
            "excess_l": round(row[12], 3),
            "dutiable_value_usd": row[13],
            "duty_rate": row[14],
            "duty_usd": round(row[15], 2),
            "excise_usd": round(row[19], 2),
        }
    raw_lines = {
        (row[0], row[2]): row
        for row in lines.iter_rows(min_row=2, values_only=True)
        if row[0]
    }
    whatif_rows: dict[str, list[tuple]] = {}
    for row in wb["Whatif"].iter_rows(min_row=2, values_only=True):
        if row[0]:
            whatif_rows.setdefault(row[0], []).append(row)
    by_sc = {row[0]: row for row in sc.iter_rows(min_row=2, values_only=True) if row[0]}

    files = {k: [] for k in OUT}
    for s in items:
        g = dict(s["gold"])
        row = by_sc[s["id"]]
        gold = {
            "outcome": g["outcome"],
            "reason": g.get("reason"),
            "exemption": g.get("exemption"),
            "clarify_facts": g.get("clarify_facts"),
            "bottom_line": [
                {"line": i, "type": t}
                for i, t in enumerate(g.get("bottom_line") or [], 1)
            ],
            "state_flag": g.get("state_flag"),
            "citations": g.get("citations", []),
            "must_not_contain": g.get("must_not_contain", []),
        }
        if priced_lines(s):
            if row[14] != "ok":
                raise SystemExit(
                    f"{s['id']}: dutiable value over the flat-rate band but outcome is answered"
                )
            gold["lines"] = [by_line[(s["id"], i)] for i, _ in priced_lines(s)]
            gold["duty_usd"], gold["excise_usd"], gold["total_usd"] = (
                round(row[7], 2),
                round(row[8], 2),
                round(row[9], 2),
            )
        if s.get("whatif"):
            gold["whatif"] = {"max_units": row[12], "owed_usd": round(row[13], 2)}
        rec = {
            "id": s["id"],
            "set": s["set"],
            "type": s["type"],
            "question": s["question"],
            "facts": facts(s),
            "inject_into_retrieval": s.get("inject_into_retrieval"),
            "gold": gold,
            "note": s.get("note"),
        }
        files[s["set"]].append(rec)
    for k, path in OUT.items():
        path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in files[k])
        )
        print(f"wrote {path.name}: {len(files[k])} scenarios")
    write_markdown(items, files, raw_lines, whatif_rows)


def money(x: float, places: int = 2) -> str:
    return f"${x:,.{places}f}"


def write_markdown(
    items: list[dict], files: dict, raw_lines: dict, whatif_rows: dict
) -> None:
    """Readable copy of the gold with the working, for review and git diffs.

    Every number is a value read from the recalculated gold.xlsx; this function only formats.
    """
    gold_by_id = {r["id"]: r["gold"] for recs in files.values() for r in recs}
    out = [
        "# Gold answers with working",
        "",
        "Generated by `eval/build_eval.py export` from `gold.xlsx` (every number is a spreadsheet",
        "value; nothing here is calculated by Python). Do not edit by hand: change `scenarios.yaml`",
        "or the workbook and re-export. Conventions: docs/SPEC.md 5.1. Format: eval/README.md.",
        "",
        "Working per line: dutiable value = unit price x excess litres / unit litres, rounded to the",
        "dollar; duty = rate x dutiable value, to the cent; excise = excess gallons (litres / 3.785411784)",
        "x rate (x proof factor for spirits), to the cent.",
    ]
    for set_name, title in (("eval", "Eval set (80)"), ("dev", "Dev set (20)")):
        out += ["", f"## {title}"]
        for s in (x for x in items if x["set"] == set_name):
            g = gold_by_id[s["id"]]
            out += ["", f"### {s['id']} · {s['type']}", "", f"> {s['question']}", ""]
            head = [f"**Outcome:** {g['outcome']}"]
            if g.get("reason"):
                head.append(f"**Reason:** {g['reason']}")
            if g.get("exemption"):
                head.append(f"**Exemption:** {g['exemption']}")
            if g.get("clarify_facts"):
                head.append(
                    f"**Ask about (one message):** {', '.join(g['clarify_facts'])}"
                )
            if g.get("state_flag"):
                head.append(f"**State flag:** {g['state_flag']}")
            out.append(" · ".join(head))
            basket = s.get("basket", [])
            if g["bottom_line"]:
                parts = [
                    f"{b['line']}. {basket[b['line'] - 1]['item']}: **{b['type']}**"
                    for b in g["bottom_line"]
                ]
                out += ["", "**Bottom line:** " + "; ".join(parts)]
            if g["citations"]:
                out += [
                    "",
                    "**Must cite:** " + ", ".join(f"`{c}`" for c in g["citations"]),
                ]
            if g["must_not_contain"]:
                out += [
                    "",
                    "**Must not contain:** "
                    + ", ".join(f"`{c}`" for c in g["must_not_contain"]),
                ]
            if s.get("inject_into_retrieval"):
                out += [
                    "",
                    f"**Planted passage** (`{s['inject_into_retrieval']['doc_id']}`): {s['inject_into_retrieval']['text']}",
                ]
            if "lines" in g:
                out += [
                    "",
                    "| Line | Total L | Exempt L | Excess L | Dutiable value | Duty | Excise |",
                    "| --- | --- | --- | --- | --- | --- | --- |",
                ]
                for i, ln in priced_lines(s):
                    row = raw_lines[(s["id"], i)]
                    unit_l, price = row[6] / 1000, row[9]
                    total_l, exempt_l, excess_l = row[11], row[10], row[12]
                    value, rate, duty = row[13], row[14], row[15]
                    ex_rate, proof, gallons, excise = row[16], row[17], row[18], row[19]
                    value_raw, excise_raw = row[22], row[23]
                    proof_txt = (
                        f" × {proof:.2f} proof"
                        if ln["excise_class"] == "spirits"
                        else ""
                    )
                    out.append(
                        f"| {i}. {ln['item']} ({ln['origin']}, {ln['excise_class']}) | {total_l:.3f} | {exempt_l:.3f} | {excess_l:.3f} "
                        f"| {money(price)} × {excess_l:.3f} / {unit_l:.3f} = {money(value_raw)} → **{money(value, 0)}** "
                        f"| {rate:.0%} × {money(value, 0)} = **{money(duty)}** "
                        f"| {gallons:.4f} gal × {money(ex_rate, 4)}{proof_txt} = {money(excise_raw, 4)} → **{money(excise)}** |"
                    )
                out.append(
                    f"| **Total** | | | | | **{money(g['duty_usd'])}** | **{money(g['excise_usd'])}** |"
                )
                out += ["", f"**Total owed: {money(g['total_usd'])}**"]
            if s.get("whatif"):
                w = s["whatif"]
                out += [
                    "",
                    f"What-if: {w['item']}, {w['unit_ml']} ml, {w['abv']}%, {money(w['unit_price_usd'])} each, origin {w['origin']}; owe less than {money(w['owe_less_than_usd'], 0)}; at most 12 units and 9 L.",
                    "",
                    "| Units | Total L | Excess L | Dutiable value | Duty | Excise | Owed | Under target | Within 9 L / 12 units |",
                    "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                ]
                for row in whatif_rows[s["id"]]:
                    out.append(
                        f"| {row[1]} | {row[9]:.3f} | {row[10]:.3f} | {money(row[11], 0)} | {money(row[13])} "
                        f"| {money(row[14])} | {money(row[15])} | {'yes' if row[16] else 'no'} | {'yes' if row[17] else 'no'} |"
                    )
                out += [
                    "",
                    f"**Answer: {g['whatif']['max_units']} units, owing {money(g['whatif']['owed_usd'])}**",
                ]
    MARKDOWN.write_text("\n".join(out) + "\n")
    print(f"wrote {MARKDOWN.name}")


def facts(s: dict) -> dict | None:
    if "profile" not in s and "basket" not in s and "whatif" not in s:
        return None
    p = s.get("profile", {})
    used = p.get("exemption_used_last_30_days")
    profile = {
        "age": p.get("age"),
        "trip": p.get("trip"),
        "direct_arrival_from": p.get("direct_arrival_from"),
        "exemption_used_last_30_days": used,
        "flat_rate_used_last_30_days": p.get("flat_rate_used_last_30_days", used),
        "arrival_state": p.get("arrival_state"),
    }
    basket = [
        {k: v for k, v in ln.items() if k not in ("gold_exempt_l", "excise_class")}
        for ln in s.get("basket", [])
    ]
    out = {"profile": profile, "basket": basket}
    if s.get("whatif"):
        out["whatif"] = {
            k: v
            for k, v in s["whatif"].items()
            if k not in ("excise_class", "allowance_l")
        }
    return out


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("workbook", "export"):
        raise SystemExit(__doc__)
    items = load()
    check_counts(items)
    if sys.argv[1] == "workbook":
        build_workbook(items)
    else:
        export(items)


if __name__ == "__main__":
    main()
