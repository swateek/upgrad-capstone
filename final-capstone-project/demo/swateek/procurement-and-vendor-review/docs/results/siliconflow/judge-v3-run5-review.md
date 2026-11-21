# Content check, run 5: review of the judge's failures

**Team:** DLlamas · Run: `e2e-v3-run5-rescored.json` (run 5, scored on eval v3) · Judge: `judge-v3-run5-rescored.md` (DeepSeek-V3.2, prompt v2, 2 passes, which agreed on 23 of 23)

The judge failed 12 of the 23 factual policy answers on content. Each one was checked against the source passage text in the index, using the same rules as the run 3 and run 4 reviews. The verdicts were prepared by Claude Code (the coding assistant) and **confirmed by the team (DLlamas) on 13 Nov 2026**. The judge passed the other 11.

## Verdicts

| Id | Judge says | Source text | Verdict | Team confirmed |
|---|---|---|---|---|
| P-001 | Error: "covered under the enabling provisions of Rule 149 … certify the reasonability of rates" | gem_gtc_4_0:C4 is titled "Enabling provisions of Rule 149 of General Financial Rules-2017"; ncs_manual_2025:4.6.3 gives Rs 50,000 and the automobile note | **Correct.** Rs 50,000 is stated. The last sentence is vague but drawn from the cited clause. | ✓ |
| P-004 | Point 1 partial; errors: Rs 1 lakh for scientific departments; the Local Purchase Committee from Rs 50,000 to Rs 5 lakh | goods_manual_2024:4.12 (Rs 1 lakh, scientific equipment); gfr_2017:R155 and goods_manual_2024:4.13 (Local Purchase Committee) | **Correct.** Same as runs 3 and 4. | ✓ |
| P-005 | Point 1 partial; error: Rs 2 lakh "for scientific equipment and computers" | gfr_2017:R154, footnote 16: "Rs. 2,00,000/- (Rupees Two lakh) only on each occasion in case of Scientific Ministries/ Departments". goods_manual_2024:4.12 has the "equipment and computers" wording, for Rs 1 lakh | **Correct, with a minor error.** The limit asked for is right (Rs 2 lakh), and the answer gives only that figure, unlike runs 3 and 4. It borrows the manual's "equipment and computers" scope and cites the manual for a figure that comes from GFR 154. | ✓ |
| P-006 | Point 1 partial, point 2 missing | gfr_2017:R155: from Rs 50,000 to Rs 5 lakh, purchase on the recommendation of a Local Purchase Committee | **Wrong.** The answer says only that "the procurement process is governed by specific rules" and never names the committee. It cites R155 without stating it. | ✓ |
| P-007 | Point 1 partial, point 2 missing; its error quote wasn't found | gfr_2017:R161, footnote 25 (Rs 1 crore for scientific ministries) | **Correct.** Same as runs 3 and 4. | ✓ |
| P-008 | Point 2 missing; error: "LTE is the default mode … up to Rs 10 lakhs" | works_manual_2025:3.10: "LTE procedures should be the default mode … upto Rs 10 lakhs", for works. goods_manual_2024:4.8 / gfr_2017:R162: up to Rs 50 lakh for goods | **Correct, with a minor error.** The answer to the goods question (up to Rs 50 lakh, plus the exceptions above that) is right. The added sentence applies the works manual's Rs 10 lakh default to goods, and cites it as works. | ✓ |
| P-009 | Point 2 partial; errors: national defence or security; selecting a particular consultant | works_manual_2025:3.12, items 5 and 6 list both, for works | **Correct, with a minor error.** The three GFR 166 grounds for goods are stated. The "additionally" sentence brings in works-manual grounds and cites them as works. | ✓ |
| P-011 | Point 2 missing; error: exemption in indigenisation/development tenders with the Competent Authority's approval | consultancy_manual_2025:6.1.1: "Submission of the bid security may be exempted with the Competent Authority's (CA's) approval, especially in the case of indigenisation/development tenders, limited tenders, and procurements directly from the manufacturer…" | **Correct.** The "error" is stated in the source. MSEs and startups are stated; registered bidders are left out, which is missing detail. | ✓ |
| P-013 | Point 1 contradicted | gfr_2017:R157: a demand must not be divided to avoid a higher authority's sanction | **Wrong.** It says splitting "is permissible if it aligns with the procurement guidelines". Run 3 had the same error, while run 4 was right. | ✓ |
| P-018 | Error: 10% for inordinate delay | gem_gtc_4_0:C15: "in case of inordinate delay maximum deduction shall be 10%" | **Correct.** The "error" is stated in the source. | ✓ |
| P-021 | Point 1 partial; error: 70/30 | The gold is 80/20 | **Wrong.** Also a miss under the citation check. | ✓ |
| P-022 | Point 2 partial; error: "applies after 01.04.2023" | goods_manual_2024:1.11.4 | **Correct, with a minor error.** Same as runs 3 and 4. | ✓ |

## Effect of the confirmed verdicts

| Run 5 | Factual policy (23) | All 60 |
|---|---|---|
| Citation check, eval v3 (`e2e-v3-run5-rescored.md`) | 22 | 57 |
| Automatic judge (`judge-v3-run5-rescored.md`) | 11 | 46 |
| **Citation check + reviewed content check** | **20** | **55** |

P-006 and P-013 move from correct to wrong. Four answers are "correct, with a minor error" (P-005, P-008, P-009, P-022). If the team marks all four wrong, the totals become 16 and 51.

The judge flagged more answers in run 5 (12 vs 9 and 11). Several of run 5's answers add a true rule from another manual, cited as such: works rules in answers about goods. The judge counts these as errors. The review treats them as minor, because the answer to the question asked is still right.
