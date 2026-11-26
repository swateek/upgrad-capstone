# Evaluation sets

| File | What it is |
| --- | --- |
| `scenarios.yaml` | Source of truth: every question, the facts it states, and the non-dollar gold (outcome, bottom line per line, clarify fact, state flag, citations) |
| `gold.xlsx` | Independent gold calculation: rates typed in from TTB and HTSUS 9816.00.20, one formula row per priced alcohol line, what-if tables |
| `gold.md` | Readable copy of the gold with the working for every priced line and what-if, exported from the workbook values. For review and git diffs; do not edit by hand |
| `eval_set.jsonl` | 80 scenarios. Frozen as git tag `eval-v2` (v1 had the old 2 L country list). **Never tune against it** (CLAUDE.md rule 6) |
| `dev_set.jsonl` | 20 separate scenarios for prompt and design work. Includes the CLAUDE.md worked examples (D01, D05, D08, D10) |
| `build_eval.py` | Copies inputs into `gold.xlsx` and exports the JSONL after the workbook is recalculated. It does no customs arithmetic |
| `eval_set_v3.jsonl` | **eval-v3**: 100 held-out scenarios under SPEC v2, for agent v2. AI-written (Claude, Gemini, Groq, Mistral, ChatGPT) from `GENERATION_PROMPT_V3.md`, split at random by type. Frozen as tag `eval-v3` after the owner's spot check. Never tuned against |
| (types in v3) | As in eval-v2, plus one widening decided at the spot check: `alcohol_excess_800` covers $800 alcohol cases including one inside the allowance (E3-047, relabelled from the $200 type after the split: 4 days is over 48 hours). The scorer does not use the type; it only groups the per-type results |
| `dev_set_v2.jsonl` | **dev-v2**: 112 scenarios from the same generation, for agent v2 tuning |
| `scenarios_v3.yaml`, `gold_v3.xlsx`, `gold_v3.md` | Source, dollar gold (same formulas as `gold.xlsx`) and readable copy for eval-v3 and dev-v2. Rebuilt by `build_v3.py`; not edited by hand |
| `generated/*.yaml`, `generated/corrections.yaml` | The generators' raw output (unedited) and the logged fixes (5 dropped, 9 corrected, each with its rule) |
| `check_v3.py` | Independent SPEC v2 rule check for generated scenarios (imports nothing from `src/`): flags disagreements for review |
| `build_v3.py` | prepare (corrections, check, split, allocation, citations) → workbook → export |
| `REVIEW_V3.md` | The owner's spot check: 15 random eval-v3 scenarios and every corrected one (`build_v3.py review`) |
| `eval_set_gold_v2.jsonl` | **gold-v2**: eval-v2's 80 questions re-scored under SPEC v2 (same questions and facts; scored changes only E07, E47: sake taxed as beer; E32, E33, E36, E37 gain the exemption, not scored). For agent v2 runs on eval-v2, labelled as such: these questions informed the v2 fixes, so eval-v3 is the headline. `eval_set.jsonl` (gold-v1) stays as tagged, for agent v1 |
| `gold_v2_changes.yaml` | Every gold-v2 change with its rule, and how the 80 were screened (`check_v3.py`, each SPEC v2 row by hand, the Day 10 failures, a random sample of passes) |
| `scenarios_gold_v2.yaml`, `gold_v2.xlsx`, `gold_v2.md` | Source, dollar gold (same formulas) and readable copy for gold-v2. Rebuilt by `build_gold_v2.py`; not edited by hand |
| `REVIEW_GOLD_V2.md` | The owner's check of gold-v2: the changed scenarios, gold-v1 next to gold-v2, and 12 random Day 10 passes; owner: all right |
| `replay.py` | Puts a run's recorded intake JSON through today's guard, clean-up and router (no model call) and scores outcome, bottom line, dollars, what-if and clarify. A cheap check between runs on dev sets; refuses held-out sets; never replaces a run |
| (eval-v3 errata) | E3-019: gold taxes a 15.5% wine at the over-16% rate (generator's excise class); the right total is $1.10, not $1.17. Not changed (eval-v3 is tagged); accuracy reported as scored and with it corrected. Found on Day 11 |
| (dev-v2 errata) | D2-055: gold answered ($1.21), but the question gives no flat-rate history after using the exemption, so SPEC 3 escalates; its facts also record "$180 for the box" as per cigar. Not changed (dev-v2 is tagged); counted as an expected miss |

The dollar gold is computed by spreadsheet formulas, never by `src/tools` (CLAUDE.md rule 5). Spreadsheet results were also checked against a separate decimal calculation outside the repo: all 61 priced lines and 5 what-if answers agree.

## Rebuild

```bash
uv add --dev pyyaml openpyxl          # once
uv run python eval/build_eval.py workbook
soffice --headless --convert-to xlsx --outdir /tmp eval/gold.xlsx && cp /tmp/gold.xlsx eval/gold.xlsx   # or open and save in Excel
uv run python eval/build_eval.py export     # writes eval_set.jsonl, dev_set.jsonl, gold.md
```

After the tag, a change to `eval_set.jsonl` means a new tag (`eval-v3`, …) and a note in the report. History: `eval-v1` → `eval-v2` corrected the 2 L country list (E15, E48).

eval-v3 and dev-v2 (SPEC v2):

```bash
uv run python eval/check_v3.py              # rule check of eval/generated/*.yaml
uv run python eval/build_v3.py prepare
uv run python eval/build_v3.py workbook
soffice --headless --convert-to xlsx --outdir /tmp eval/gold_v3.xlsx && cp /tmp/gold_v3.xlsx eval/gold_v3.xlsx
uv run python eval/build_v3.py export
```

gold-v2 (eval-v2's questions under SPEC v2):

```bash
uv run python eval/build_gold_v2.py prepare
uv run python eval/build_gold_v2.py workbook
soffice --headless --convert-to xlsx --outdir /tmp eval/gold_v2.xlsx && cp /tmp/gold_v2.xlsx eval/gold_v2.xlsx
uv run python eval/build_gold_v2.py export
uv run python eval/build_gold_v2.py diff     # fails if an id not in gold_v2_changes.yaml moved
uv run python eval/build_gold_v2.py review
```

Agent v2 runs: `run_agent.py --set dev2` (tune), `--set eval3` (held out, headline) and `--set eval-gold2` (eval-v2 re-scored, labelled); the last two need the v2 freeze and `LLM_CACHE=0`.

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
  "gold": {"outcome": "answered", "reason": null, "exemption": "standard_800", "clarify_facts": null,
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

Correct = outcome and every bottom-line type match; every dollar figure within $0.01; gold citations ⊆ cited ids, and no cited id outside the retrieved set; clarify asked exactly when gold says so, in one message that asks for every fact in `clarify_facts` and nothing outside the current stage (SPEC 5.2).

## Coverage

Eval types and counts follow docs/SPEC.md 7. Cases worth knowing:

- Mexico: E04 (USMCA Free, over 48 h), E05 (Tijuana day trip: 48-hour rule waived), E55 and E65.
- Highest-rate-first allocation across lines: E06, E43–E47, E51, E52.
- Excise classes: still wine ≤ 16% (most), 16–21% (E08), sparkling (E09, E45), beer (E10, E51), spirits incl. low ABV (E12) and cream liqueur (E52), sake as wine (E07, E47).
- Free programmes other than USMCA: E12 (KR), E15 (DO), E48 (PE), D20 (CL).
- 2 L trap: E15 (Dominican Republic) and E48 (Peru) arrive directly from countries on CBP's old list that are not beneficiary countries under HTSUS ch. 98 Note 4 / General Note 7(a), so 1 L applies (eval-v2).
- $200 limits at and over the edge: E21 (exactly 150 ml), E22 (200 ml), E24 (under 150 ml but over $200).
- Escalations: E38 (Russian vodka), E49 (over the $1,000 flat-rate band), E50 (over 9 L).
- Several facts missing at once: E57 and D13 (age, trip length and 30-day use asked together).
- `flat_rate_used_last_30_days`: E20 and E24 state that no duty was paid on the earlier trip, so the flat rate is available.

## Answers that rest on a project choice

These follow the approved SPEC, but the regulation alone does not settle them. If a choice changes, re-export and re-tag.

| Scenarios | Depends on | If it went the other way |
| --- | --- | --- |
| Every multi-line allocation (E06, E43–E47, E51, E52) | SPEC 5.4: "highest rate" in 148.33(b) ranked by duty + excise **per litre**, because the 1 L cap is the binding limit | Ranking per dollar of value flips E44 ($3.57 → $3.84) and E46 ($1.58 → $2.16) |

## Not covered (spec gaps, decide before v2)

- Tobacco that loses its exemption because the $200 exemption fails on another item (e.g. 5 cigars plus a 750 ml bottle on a day trip). The rules treat the tobacco as over the allowance (declare, detention risk), which is probably harsher than CBP practice.
- Baskets where tobacco within the count limits uses up the $800 value, so part of it is dutiable.
- Two-turn clarify: the follow-up answer, the final answer after it, and the defaults after two unanswered rounds (SPEC 5.2).
- Corrections across turns ("actually it was 3 days").

## Hand re-check (solo gold protocol)

The day after building, re-check these 20 by hand (the working is in `gold.md`) from the regulation text, and record the date and result in `WORKLOG.md`:
E01, E06, E11, E13, E16, E18, E20, E22, E24, E35, E39, E43, E44, E45, E46, E48, E52, E53, E65, D05.
