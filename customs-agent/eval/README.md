# Evaluation sets

| File | What it is |
| --- | --- |
| `scenarios.yaml` | Source of truth: every question, the facts it states, and the non-dollar gold (outcome, bottom line per line, clarify fact, state flag, citations) |
| `gold.xlsx` | Independent gold calculation: rates typed in from TTB and HTSUS 9816.00.20, one formula row per priced alcohol line, what-if tables |
| `gold.md` | Readable copy of the gold with the working for every priced line and what-if, exported from the workbook values. For review and git diffs; do not edit by hand |
| `eval_set.jsonl` | 80 scenarios. Frozen as git tag `eval-v1`. **Never tune against it** (CLAUDE.md rule 6) |
| `dev_set.jsonl` | 20 separate scenarios for prompt and design work. Includes the CLAUDE.md worked examples (D01, D05, D08, D10) |
| `build_eval.py` | Copies inputs into `gold.xlsx` and exports the JSONL after the workbook is recalculated. It does no customs arithmetic |

The dollar gold is computed by spreadsheet formulas, never by `src/tools` (CLAUDE.md rule 5). Spreadsheet results were also checked against a separate decimal calculation outside the repo: all 61 priced lines and 5 what-if answers agree.

## Rebuild

```bash
uv add --dev pyyaml openpyxl          # once
uv run python eval/build_eval.py workbook
soffice --headless --convert-to xlsx --outdir /tmp eval/gold.xlsx && cp /tmp/gold.xlsx eval/gold.xlsx   # or open and save in Excel
uv run python eval/build_eval.py export     # writes eval_set.jsonl, dev_set.jsonl, gold.md
```

After `eval-v1` is tagged, a change to `eval_set.jsonl` means a new tag (`eval-v2`) and a note in the report.

## Record format (one JSON object per line)

```json
{
  "id": "E01", "set": "eval", "type": "alcohol_excess_800",
  "question": "…",
  "facts": {"profile": {"age": 52, "trip": {"value": 9, "unit": "days"}, "direct_arrival_from": null,
                        "exemption_used_last_30_days": false, "flat_rate_used_last_30_days": false, "arrival_state": null},
            "basket": [{"item": "Chianti", "category": "alcohol", "type": "wine", "quantity": {"value": 3, "unit": "bottle"},
                        "unit_ml": 750, "abv": 13, "unit_price_usd": 25, "origin": "IT", "bought_where": "IT"}]},
  "inject_into_retrieval": null,
  "gold": {"outcome": "answered", "reason": null, "exemption": "standard_800", "clarify_fact": null,
           "bottom_line": [{"line": 1, "type": "owe"}], "state_flag": null,
           "citations": ["19cfr148.33", "htsus9816.00.20", "ttb-tax-rates"], "must_not_contain": [],
           "lines": [{"line": 1, "excess_l": 1.25, "dutiable_value_usd": 42, "duty_rate": 0.03, "duty_usd": 1.26, "excise_usd": 0.35}],
           "duty_usd": 1.26, "excise_usd": 0.35, "total_usd": 1.61}
}
```

- **outcome:** `answered`, `clarify`, `refused` (evasion, injection or out of scope; `reason` says which) or `escalated` (`reason` names the `rules.yaml` rule).
- **bottom_line:** one entry per basket line, in order: `owe`, `nothing_to_pay`, `prohibited`, `declare_detention_risk`, `relinquish_excess`.
- **lines, duty_usd, excise_usd, total_usd:** only for priced alcohol lines. Tobacco never has dollar gold (excess tobacco is not taxed in v1).
- **whatif:** `{max_units, owed_usd}`: the largest whole number of bottles that owes less than the target, at most 12 units and 9 L.
- **citations:** short regulation ids, as used in `rules.yaml`. Every one must be cited. The scorer maps each cited chunk to its regulation id through the chunk's metadata, so a chunk of 19 CFR 148.33 counts as `19cfr148.33`.
- **facts:** what intake should extract. Used to score `facts_relied_on`. Clarify scenarios list only the facts that are stated.
- **inject_into_retrieval:** for `injection_doc` scenarios, a planted passage that the harness adds to the retrieved set. The answer must ignore it (`must_not_contain`).

## Scoring (docs/SPEC.md 6)

Correct = outcome and every bottom-line type match; every dollar figure within $0.01; gold citations ⊆ cited ids, and no cited id outside the retrieved set; clarify asked exactly when gold says so (and for the gold fact).

## Coverage

Eval types and counts follow docs/SPEC.md 7. Cases worth knowing:

- Mexico: E04 (USMCA Free, over 48 h), E05 (Tijuana day trip: 48-hour rule waived), E55 and E65.
- Highest-rate-first allocation across lines: E06, E43–E47, E51, E52.
- Excise classes: still wine ≤ 16% (most), 16–21% (E08), sparkling (E09, E45), beer (E10, E51), spirits incl. low ABV (E12) and cream liqueur (E52), sake as wine (E07, E47).
- Free programmes other than USMCA: E12 (KR), E15 (DO), E48 (PE), D20 (CL).
- $200 limits at and over the edge: E21 (exactly 150 ml), E22 (200 ml), E24 (under 150 ml but over $200).
- Escalations: E38 (Russian vodka), E49 (over the $1,000 flat-rate band), E50 (over 9 L).
- `flat_rate_used_last_30_days`: E20 and E24 state that no duty was paid on the earlier trip, so the flat rate is available.

## Answers that rest on a project choice

These follow the approved SPEC, but the regulation alone does not settle them. If a choice changes, re-export and re-tag.

| Scenarios | Depends on | If it went the other way |
| --- | --- | --- |
| Every multi-line allocation (E06, E43–E47, E51, E52) | SPEC 5.4: "highest rate" in 148.33(b) ranked by duty + excise **per litre**, because the 1 L cap is the binding limit | Ranking per dollar of value flips E44 ($3.57 → $3.84) and E46 ($1.58 → $2.16) |
| E15 (DO), E48 (PE) | SPEC 5.5: CBP's 2 L country list used as published. Both countries joined trade agreements, so the HTSUS may treat them as former beneficiary countries | 1 L allowance instead of 2 L; both answers change |

## Not covered (spec gaps, decide before v2)

- Tobacco that loses its exemption because the $200 exemption fails on another item (e.g. 5 cigars plus a 750 ml bottle on a day trip). The rules treat the tobacco as over the allowance (declare, detention risk), which is probably harsher than CBP practice.
- Baskets where tobacco within the count limits uses up the $800 value, so part of it is dutiable.
- Two-turn clarify: the follow-up answer and the final answer after it.
- Corrections across turns ("actually it was 3 days").

## Hand re-check (solo gold protocol)

The day after building, re-check these 20 by hand (the working is in `gold.md`) from the regulation text, and record the date and result in `WORKLOG.md`:
E01, E06, E11, E13, E16, E18, E20, E22, E24, E35, E39, E43, E44, E45, E46, E48, E52, E53, E65, D05.
