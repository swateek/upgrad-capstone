# Eval set freeze

The Track B Week-1 gate: the evaluation set is frozen before any agent harness code is written.

## Version 1: frozen 13 November 2026

| | |
|---|---|
| Commit | `0e3d764` ("#17 - phase 1 - evals") on branch #17. No git tag or branch is used for the eval set. |
| Questions | 60: 25 policy, 20 screening, 15 bid. 8 are refusals. |
| Also frozen | 15 retrieval-only labels, 8 dev (few-shot) questions, 10 synthetic bid cases with gold score sheets, the screening snapshot (GeM latest version 03-Sep-2024 + the synthetic buyer list), `refusals.yaml` |
| `eval/queries.jsonl` sha256 | `4ebb75965543cee2678a4623670809ccf540a10649aec93691e59ec116c334a2` |
| Every frozen file | `domains/procurement/eval/freeze.lock.yaml` (68 files with sha256) |
| Enforced by | `backend/tests/test_eval_freeze.py` |
| Corpus the gold refers to | `by_rule` chunks built from the files pinned in `corpus/manifest.lock.yaml` (1,690 documents) |

The gold was checked mechanically before the freeze:
- every policy citation exists in the index and contains the stated fact;
- every screening answer equals the output of `screening.match()`;
- every bid score sheet was recomputed from its rubric by `pipelines/validate_bid_cases.py`.

## Changing the gold after the freeze

Don't edit a frozen file in place. If a gold answer is found to be wrong:

1. Fix it, bump `version` in `freeze.lock.yaml`, and regenerate the hashes in the same commit.
2. Add a section below with the date, the question ids, what changed, and why.
3. Report results with the eval version and commit they were run on. Never mix versions in one table.

## Changes since version 1

### Version 2: 13 November 2026

| | |
|---|---|
| Changed | **P-015** only: `gold.also_accept` += `goods_manual_2024:1.11.3`, `consultancy_manual_2025:1.10.2` |
| Why | Both manual sections state the rule word for word ("50 (fifty) per cent and 20 (twenty) per cent for 'Class-I local supplier'/'Class-II local supplier'"). The pre-freeze scan for restatements missed them because they write "50 (fifty) per cent" instead of "50%". In run 2 the agent answered P-015 correctly, citing these two sections, and was scored wrong. |
| Not changed | Every other question, gold answer, bid case and screening file. |
| `eval/queries.jsonl` sha256 | `31c47e5fb0325a4b…` (full hash in `freeze.lock.yaml`) |
| Reporting | Runs 1–2 were scored on v1. Run 2 is also re-scored on v2 from its saved answers (no new API calls), so v1 and v2 numbers sit side by side. Later runs use v2. |

### Version 3: 13 November 2026

| | |
|---|---|
| Changed | **P-011**: `gold.also_accept` = `goods_manual_2024:6.1.1`, `ncs_manual_2025:6.1.1`, `consultancy_manual_2025:6.1.1` (it had none). **P-012**: `gold.also_accept` += `goods_manual_2024:6.1.2`. |
| Why | Each section is headed "Bid Security (Rule 170 of GFR 2017)" or "Performance Security (Rule 171 of GFR 2017)" and restates the gold rule. The P-011 sections give the exemption for MSEs and DPIIT-recognised startups word for word. goods_manual_2024:6.1.2 gives "three (3) to five (5) per cent" for goods. v1 already accepted goods_manual_2024:4.4.1 for P-012, which only cross-refers to 6.1.2. In run 5, both questions were answered correctly with these citations and scored wrong. A heading scan ("(Rule N of GFR …)") then checked every gold GFR rule. The other candidates found were not added: the consultancy and non-consultancy 6.1.2 sections cover services contracts, and P-012 asks about goods; no candidate states P-010's 2–5% figure. |
| Not changed | Every other question, gold answer, bid case and screening file. |
| `eval/queries.jsonl` sha256 | `4c9c833f441dd304…` (full hash in `freeze.lock.yaml`) |
| Reporting | Runs 3–5 are re-scored on v3 from their saved answers (no new API calls) and reported next to their v2 scores. Versions are never mixed in one comparison. |
