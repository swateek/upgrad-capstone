# Eval freeze log

The frozen evaluation set and every change to it. `pack/eval/freeze.lock.yaml` holds the hashes; `backend/tests/test_eval_freeze.py` fails if a frozen file, its gold, or a signed-off rule table changes without a new version here.

## Version 1 (`eval-v1`), frozen 2026-11-17

**Written against:** SPEC v1.0 (approved 2026-11-17) and the rules signed off on 2026-11-17 (decisions A–G, `docs/regulatory-checks.md`).

**Contents**
- `pack/eval/queries.jsonl`: 80 scenarios in the mentor's categories and counts.
  - alcohol_excess_800 12, alcohol_cbi_2L 4, exemption_200_all_or_nothing 8, tobacco_over_limit 7;
  - cuban_origin 7, under_21 4, mixed_basket 10, whatif 4;
  - clarify 8, state_flag 3, out_of_scope 5, refuse_evasion 4, injection_doc 2, injection_user 2.
- `pack/eval/corrections.jsonl`: 6 multi-turn correction scenarios (plan D17), scored separately.
- `pack/eval/retrieval_labels.jsonl`: acceptable clause ids per gold claim (frozen and dev).
- Sources: `pack/eval/src/frozen.yaml`, `src/corrections.yaml`; gold `pack/eval/gold/gold.jsonl`.
- The rule tables `pack/rules/*.yaml`: the gold depends on them.
- Not frozen: `dev.jsonl` (20, for tuning and few-shots).

**Frozen gold outcomes per turn:** answered 68, clarify 11, refused 6, out_of_scope 5, escalated 1.

**How the gold was made (plan D18)**
1. Scenarios (turns + stated facts) written by the main session.
2. Gold built by a separate agent that read only the SPEC, the regulatory checks, the rule tables, the scenarios and the corpus, never any app code. It used its own script (`pack/eval/gold/build_gold.py`, Decimal arithmetic, per-line half-up rounding), a formula workbook (`gold.xlsx`, 127 formula rows reproduce the gold) and an issues log (`ISSUES.md`).
3. User decisions on the builder's issues:
   - A1: tobacco on a broken $200 exemption is all at seizure risk;
   - G09: soju is a distilled spirit;
   - I03: owe $0.35 excise plus "3% of the value";
   - coverage: A11 now tests the 4% Column 2 rate and I03 the value-unknown note;
   - the DV07 text fixed.
4. Hand-check of 20 (`pack/eval/gold/hand-check-20.md`) by the main session at the user's request, in place of the user's own check. Every figure was recomputed with a separate script (`pack/eval/gold/review_hand_check.py`), citations were checked against the corpus, and outcomes against the regulation text. **20/20 OK.**
   - Finding F1 (R11 required on single-alcohol-line turns) was fixed by the builder after the user's approval: 37 turns lost one R11 claim, nothing else changed (diffed independently).
   - Finding F2 (Illinois flag rests on the ILCC form; ilga.gov unreachable) is a documented limitation.

**Known limitations**
- The business case's examples appear in corrected form (`docs/regulatory-checks.md`).
- The Illinois flag evidence is thin (F2).
- The CBP 2-litre country list (Decision A) is wider than the HTS General Note 7(a) list. Four scenarios depend on it (B03, G03, I07, DV14; see `ISSUES.md`).
- `whatif` (4) is scored only if the stretch tool ships.

## Changing the frozen set

A gold or rule change needs all of:
1. a new version number;
2. regenerating the lock (`uv run python -m eval.build_eval_sets --freeze <N>`) in the same commit;
3. an entry here with the reason.

Never change gold to make a run pass.
