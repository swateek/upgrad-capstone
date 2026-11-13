# Eval set freeze

The Track B Week-1 gate: the evaluation set is frozen before any agent harness code is written.

## eval-v1: frozen 13 November 2026

| | |
|---|---|
| Git tag | `eval-v1` → commit `0e3d764` ("#17 - phase 1 - evals") |
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

1. Fix it, regenerate `freeze.lock.yaml`, and tag the commit `eval-v2`.
2. Add a section below with the date, the question ids, what changed, and why.
3. Report results against the tag they were run on. Never mix versions in one table.

## Changes since eval-v1

None.
