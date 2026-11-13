# Content check, run 3: review of the judge's failures

**Team:** DLlamas · Run: `e2e-v2-run3.json` (eval v2) · Judge: `judge-v2-run3.md` (DeepSeek-V3.2, prompt v2, 2 passes)

The judge failed 9 of the 23 factual policy answers on content. Each one was checked against the source passage text in the index. The verdicts were prepared by Claude Code (the coding assistant) and **confirmed by the team (DLlamas) on 13 Nov 2026**.

The judge passed the other 14. Those weren't re-reviewed, because a pass needs point 1 stated, no contradiction and no error with a verified quote.

## Verdicts

| Id | Judge says | Source text | Verdict | Team confirmed |
|---|---|---|---|---|
| P-004 | Point 1 partial, and two errors: Rs 1 lakh for scientific departments; the Local Purchase Committee from Rs 50,000 to Rs 5 lakh | goods_manual_2024:4.12: "This limit for Scientific Ministries/ Departments has been enhanced to Rs 1,00,000/- (Rupees One Lakh) for scientific equipment and computers on each occasion". gfr_2017:R155: "above Rs.50,000 … upto Rs.5,00,000/- … on the recommendations of a duly constituted Local Purchase Committee" | **Correct.** Both "errors" are stated in the sources. The answer gives Rs 50,000 and the competent authority's certificate for the case asked, and labels the scientific figure as a separate case. | ✓ |
| P-005 | Point 1 partial; error: "enhanced to Rs 1,00,000 for each case" | goods_manual_2024:4.12 gives Rs 1 lakh "for scientific equipment and computers"; gfr_2017:R154 (updated to 31 Jan 2026) gives Rs 2 lakh | **Wrong.** The question is about scientific departments. The answer leads with Rs 1 lakh as their limit, then also gives Rs 2 lakh, so the reader gets two figures for the same case. The gold is Rs 2 lakh. | ✓ |
| P-007 | Point 1 partial (rule exceptions not listed); point 2 partial; its error quote wasn't found | gfr_2017:R161, footnote 25: "Rs. 1,00,00,000/- (Rupees one crore) and above in case of Scientific Ministries/ Departments/ Organization" | **Correct.** Rs 50 lakh is stated for the general case, and Rs 1 crore for scientific ministries is in the rule's own amendment footnote. Leaving out the list of exceptions is missing detail, not an error. | ✓ |
| P-013 | Point 1 contradicted; "no explicit restriction on splitting" | gfr_2017:R157 forbids dividing a demand to avoid a higher authority's sanction | **Wrong.** The answer states the opposite of the rule it cites, and it invents a "Department of Public Relations (DFPR)". | ✓ |
| P-014 | Point 1 contradicted; "the order applies at Rs 4 lakh" | consultancy_manual_2025:1.10.2: purchases "less than Rs. 5 lakhs" are exempt | **Wrong.** The answer opens with the wrong yes/no, then quotes the exemption that contradicts it. | ✓ |
| P-018 | One error: "the quantum of LD is also influenced by variations in the contract and the nature of the delay" | ncs_manual_2025:9.4.7, titled "Quantum of LD", covers LD when delivery is extended for delays attributable to the contractor. gem_gtc_4_0:C15 covers 0.5% per week, the 5% cap, and 10% for inordinate delay | **Correct.** Every figure the answer gives is in GTC C15. The flagged sentence is vague but drawn from the cited section, and it doesn't change the answer. | ✓ |
| P-021 | Point 1 partial; error: 70/30 | The gold is 80/20 for highly complex assignments | **Wrong.** This was already a miss under the citation check. | ✓ |
| P-022 | Point 2 partial; error: "applies to all procurements … after 01.04.2023". **The two judge passes disagree.** | goods_manual_2024:1.11.4: registration "has been applicable since 23.07.2020"; 01.04.2023 applies only to bidders with a specified transfer-of-technology arrangement (para b) | **Correct, with a minor error.** The question (can such a bidder bid?) is answered correctly: only if registered with the Competent Authority. The 01.04.2023 date is wrongly attached to every bidder, but it doesn't change the answer to the question. | ✓ |
| P-023 | Point 1 contradicted | The office note says the sheet stored with each case is used | **Wrong.** This was already a miss under the citation check; it scored case_001 instead. | ✓ |

## Effect of the confirmed verdicts

| | Factual policy (23) | All 60 |
|---|---|---|
| Citation check only (`e2e-v2-run3.md`) | 21 | 56 |
| Automatic judge (`judge-v2-run3.md`) | 14 | 49 |
| **Citation check + reviewed content check** | **18** | **53** |

The three answers that move from correct to wrong are P-005, P-013 and P-014. If the team marks P-022 wrong, the totals become 17 and 52.

## Why the judge is not used on its own

- **Prompt v1** (`judge-v2-run3-prompt1.md`) listed claims that the sources support as "material errors", even though its instructions said not to: the automobile exception in P-001, and the 10% cap for inordinate delay in P-018. It scored 11/23.
- **Prompt v2** made each error quote the source text that shows the claim is false, and code checks that the quote exists. That removed most of the false errors (14/23).
- **It still over-flags.** The judge sometimes quotes a real sentence that doesn't actually contradict the claim (P-004), and it treats missing detail as "partial" (P-007).

So the judge is used to *find* content problems, and a person decides them. It caught all three real content errors that the citation check missed: P-005, P-013 and P-014.
