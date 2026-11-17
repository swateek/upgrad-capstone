# Rule and rate tables

The calculators read these files; no rule or number is hard-coded. Every row cites clause ids from the corpus (`data/chunks/documents.jsonl`, `source:unit`). The research behind each row is in `docs/regulatory-checks.md`.

Status per row: `proposed` (researched, awaiting the user's sign-off) or `signed_off` (with date). Eval items for a row are written only after sign-off. All rows were signed off on 2026-11-17, with decisions A–G recorded in `docs/regulatory-checks.md`. A change to any row needs a new sign-off.

| File | What |
|---|---|
| `rules.yaml` | R1–R12: eligibility, limits, outcomes |
| `rates.yaml` | Duty and excise rates, as-of date |
| `units.yaml` | Unit conversions and defaults |
| `countries.yaml` | Mexico, insular possessions, Caribbean Basin beneficiaries, Column 2, trade-agreement programmes |
| `brands.yaml` | Brand names that do not settle origin (team heuristic, not law) |
| `states.yaml` | The five arrival-state flags |
| `facts.yaml` | Answer-changing facts: when to ask, what to do if still missing |
