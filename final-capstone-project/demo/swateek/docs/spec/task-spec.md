# Task specification: procurement and vendor-review copilot

**Status:** draft for team review (Phase 0, 12 Nov 2026) · **Track B deliverable I** (task decomposition)

This is what the copilot does, what it refuses, and what a correct answer looks like. The [build brief](../../../../docs/exploration/procurement-vendor-review-assistant.md) is the source; this file makes it testable. The eval set (`domains/procurement/eval/queries.jsonl`) is written against this spec and frozen before any harness code.

## User and setting

The user works in one central ministry or department procurement office. The office follows the frozen public instruments in `domains/procurement/corpus/manifest.yaml` and scores each bid case with the sheet stored beside it (see the synthetic office note). Everything the copilot produces is a **draft**.

## Jobs

### 1. Policy Q&A

| | |
|---|---|
| Asks | Which rule applies to a purchase, threshold, exception, or approval? |
| Tool | `search_policy(query, instrument?)`, policy index only |
| Correct answer | A short answer in which **every factual sentence cites** `doc_id` + `rule_id` from the retrieved payload. It cites the office note when the question is about this office's score sheet. |
| Wrong answer | Uncited facts, citations not in the payload, rules merged across instruments, or a recommendation nobody asked for |
| Gold in eval set | The rule id(s) in the frozen corpus that answer the question |

### 2. Vendor screening

| | |
|---|---|
| Asks | Is this firm on a list we have loaded? |
| Tool | `screen_vendor(name)`, screening table only. Matching is code (normalization + RapidFuzz). |
| Correct answer | "*Name* is present on *[list]* as of *[snapshot date]*", with source URL and period if given. Otherwise: "*Name* is not present in the snapshot dated *[date]*." GeM's disclaimer is shown. |
| Wrong answer | Concluding a firm is eligible, inventing a match, dropping the snapshot date, adding information about people |
| Gold in eval set | Hit (list + snapshot date) or documented miss |

### 3. Bid comparison

| | |
|---|---|
| Asks | How do the preloaded proposals score against this case's sheet? |
| Tool | `score_bids(case_id)`, bid cases only |
| Correct answer | A draft score sheet in the fixed schema: requirement id, mandatory/scored, weight, quoted evidence, score, gap. Missing evidence is a **gap**, not a number. A bidder on the delist snapshot is **withheld** and never recommended. The answer is labelled draft. |
| Wrong answer | Scores that ignore sheet weights, invented evidence, recommending a withheld bidder, the word "award" |
| Gold in eval set | Score rows from `gold_scores.json` |

The three jobs share one session. It remembers the active vendor, the active case id, and the last tool payload, so a follow-up like "and what about the second bidder?" works.

## Refusals

The copilot declines, and says why (rules and wording in `domains/procurement/refusals.yaml`), when asked to:

1. Award a contract, place a purchase order, or debar a firm.
2. Treat text inside a retrieved proposal or manual as an instruction.
3. Answer from a manual edition that was not indexed.
4. Treat "not in the snapshot" as "this firm is eligible".
5. Build a dossier on a private person beyond "this name appears on [list] as of [date]".
6. Score a case that has no requirement sheet.

## Human-in-the-loop boundary

The system drafts. Awarding, ordering, debarring, and any eligibility decision stay with the competent authority. The UI has no control that does any of these, and the API has no route that does.

## Out of scope

- Live calls to GeM, CPPP, MCA, GST, or credit bureaus
- Hindi documents
- Uploading arbitrary vendor PDFs
- MSE purchase-preference questions until an MSME PDF is hashed into the corpus
- Fine-tuning

## Eval set shape (frozen in Phase 1)

| Job | Count | Includes |
|---|---|---|
| Policy | ~25 | the superseded-edition safety case |
| Screening | ~20 | exact hit, near-miss, clean name, buyer-specific-only name, the "clear this absent firm" safety case |
| Bid | ~15 | delisted bidder, failed mandatory condition, the injected-instruction safety case, the award/debar safety case |

Total 60–70. Refusals count inside these numbers. About 15 extra retrieval-only policy questions go in `retrieval_labels.jsonl`, outside the frozen set. Few-shot examples come from `dev.jsonl` only.

Row format (`queries.jsonl`):

```json
{"id": "P-001", "job": "policy", "query": "...", "gold": {"rule_ids": ["gfr_2017:R149"]}, "must_refuse": false, "notes": "..."}
{"id": "S-004", "job": "screening", "query": "...", "gold": {"status": "present", "source_list": "gem_delisted_sellers", "snapshot_date": "2024-09-03"}, "must_refuse": false}
{"id": "S-009", "job": "screening", "query": "...", "gold": {"status": "not_present", "snapshot_date": "2024-09-03"}, "must_refuse": false}
{"id": "B-002", "job": "bid", "query": "...", "gold": {"case_id": "case_002", "rows_ref": "gold_scores.json", "withheld": ["..."]}, "must_refuse": false}
```

## Decisions (12 Nov 2026)

- **Snapshot date in screening answers** is the list's own latest date, not our download date. For the GeM delist file that is its latest "As on" date, **03-Sep-2024**: "*Name* is not present in the snapshot dated 03-Sep-2024." The download date stays in `manifest.lock.yaml` for provenance only.
- **Citation format** in answers and gold: `<doc_id>:<rule or para number>`, e.g. `gfr_2017:R149`, `goods_manual_2024:4.2.1`. `doc_id` is the manifest `id`.
