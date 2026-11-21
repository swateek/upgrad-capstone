# Content check, run 4: review of the judge's failures

**Team:** DLlamas · Run: `e2e-v2-run4.json` (eval v2) · Judge: `judge-v2-run4.md` (DeepSeek-V3.2, prompt v2, 2 passes)

The judge failed 11 of the 23 factual policy answers on content. Each one was checked against the source passage text in the index, using the same rules as the run 3 review (`judge-v2-run3-review.md`). The verdicts were prepared by Claude Code (the coding assistant) and **confirmed by the team (DLlamas) on 13 Nov 2026**. The judge passed the other 12.

## Verdicts

| Id | Judge says | Source text | Verdict | Team confirmed |
|---|---|---|---|---|
| P-001 | Error: "the rules do not mention any specific exceptions … except for the automobile exception" | ncs_manual_2025:4.6.3 gives Rs 50,000, and its Note 1 covers automobiles | **Correct.** Rs 50,000 is stated with its conditions. The flagged sentence is a vague closing remark, not a false rule. | ✓ |
| P-004 | Points 1 and 2 partial; its error quote wasn't found | goods_manual_2024:4.12 gives Rs 50,000, and Rs 1 lakh for scientific equipment. goods_manual_2024:4.17.2: GeMAR&PTS is "mandatory … for procurement outside GeM". gfr_2017:R154 covers the competent authority's certificate | **Correct.** Same as run 3. The certificate is paraphrased ("reasonable and meets the required specifications") but not misstated. | ✓ |
| P-005 | Point 1 partial; error: Rs 1 lakh | goods_manual_2024:4.12 gives Rs 1 lakh for scientific equipment and computers; gfr_2017:R154 (updated to 2026) gives Rs 2 lakh | **Wrong.** Same as run 3: two limits for the same case, with Rs 1 lakh first. The gold is Rs 2 lakh. | ✓ |
| P-006 | Point 2 partial; error: GeMAR&PTS is a prerequisite. **The two judge passes disagree.** | goods_manual_2024:4.17.2: "GeMAR&PTS shall be a pre-requisite for … floating a bid outside GeM" | **Correct.** The "error" is stated in the source. | ✓ |
| P-007 | Point 1 partial, point 2 missing; its error quote wasn't found | gfr_2017:R161, footnote 25: Rs 1 crore for scientific ministries | **Correct.** Same as run 3. | ✓ |
| P-008 | Point 1 partial; error: "between Rs 5 lakh and Rs 50 lakh" | goods_manual_2024:4.8: "LTE procedures should be the default mode … between Rs. 5 lakh to Rs. 50 lakhs (Rule 162 of GFR 2017)" | **Correct.** The range is the manual's own wording, and the answer also covers LTE above Rs 50 lakh in exceptional cases. | ✓ |
| P-014 | Point 2 missing; error: "the order applies to purchases up to Rs 200 crore, as stated in Rule 161(iv)(b)" | works_manual_2025:1.11.2: below Rs 200 crore, a *global tender enquiry* shall not be issued without approval. consultancy/ncs manual: purchases "less than Rs. 5 lakhs shall be exempt" | **Correct, with a minor error.** The answer to the question is right: the order doesn't apply at Rs 4 lakh. The opening sentence misreads the Rs 200 crore clause, which is about global tenders, not the order's scope. Run 3 got the yes/no wrong. | ✓ |
| P-018 | Error: 10% for inordinate delay | gem_gtc_4_0:C15: "in case of inordinate delay maximum deduction shall be 10%" | **Correct.** The "error" is stated in the source. | ✓ |
| P-021 | Point 1 partial; error: 70/30 | The gold is 80/20 | **Wrong.** Also a miss under the citation check. | ✓ |
| P-022 | Point 2 partial; error: "applies after 01.04.2023" | goods_manual_2024:1.11.4: 01.04.2023 applies to bidders with a transfer-of-technology arrangement (para b); registration in general since 23.07.2020 | **Correct, with a minor error.** Same as run 3. | ✓ |
| P-023 | Point 1 missing ("cannot find") | office_note_001:P3 | **Wrong.** Also a miss under the citation check. | ✓ |

## Effect of the confirmed verdicts

| | Factual policy (23) | All 60 |
|---|---|---|
| Citation check only (`e2e-v2-run4.md`) | 21 | 55 |
| Automatic judge (`judge-v2-run4.md`) | 12 | 46 |
| **Citation check + reviewed content check** | **20** | **54** |

Only P-005 moves from correct to wrong. P-013 (splitting a demand) and P-014 (Make in India at Rs 4 lakh) were content errors in run 3; in run 4 the judge passed P-013, and P-014 has the right answer with a minor error. If the team marks P-014 and P-022 wrong, the totals become 18 and 52.

Run-to-run differences of this size come from sampling, not from the run 4 code change, which only touches `score_bids` (small-model-log #38).
