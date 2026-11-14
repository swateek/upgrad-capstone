# Content check: `e2e-v2-run4.json`

2026-11-13T10:25:44+00:00 · judge `deepseek-ai/DeepSeek-V3.2` (prompt v2) · 2 passes · system model `Qwen/Qwen3-8B` · eval v2

Rule: content correct = point 1 stated, no point contradicted, no material error with a verified quote; final = citation correct AND content correct (pass 1).

| Metric | Value |
|---|---|
| Citation correct (e2e scorer) | 21/23 |
| Content correct (judge) | 12/23 |
| **Final: citation and content correct** | **12/23** |
| Judge passes agree | 21/23 |
| Judge tokens (prompt / completion) | 86,441 / 6,968 |

| Id | Citation | Content | Final | Passes agree | Judge notes (pass 1) |
|---|---|---|---|---|---|
| P-001 | ✓ | ✗ | ✗ | yes | error: The rules do not mention any specific exceptions or special cases for vendor screening or bid scoring in direct procurement scenarios, except for the automobile exception |
| P-002 | ✓ | ✓ | ✓ | yes | point 2 partial: The answer does not mention that online bidding or reverse auction tools may also be used, which is part of the reference point's core content. |
| P-003 | ✓ | ✓ | ✓ | yes |  |
| P-004 | ✓ | ✗ | ✗ | yes | point 1 partial: The answer states the Rs. 50,000 threshold for general procurements but also introduces a different, higher threshold for Scientific Ministries/Departments, which is not part of the reference point's core content. · point 2 partial: The answer mentions a certificate from the competent authority but incorrectly specifies its content as confirming the purchase is 'reasonable and meets the required specifications' instead of the required format stating the goods are of requisite quality, from a reliable supplier at a reasonable price. · error (quote not found, not counted): the necessary documentation includes a 'GeM Availability Report and Past Transaction Summary' (GeMAR&PTS) with a unique ID generated on the GeM portal |
| P-005 | ✓ | ✗ | ✗ | yes | point 1 partial: The answer states the limit is Rs. 2,00,000 for scientific ministries/departments, but does not specify that this is for 'notified' ones, though the list provided in the source includes DRDO and ICAR. · point 2 partial: The answer mentions the limit is for procurement outside GeM, but does not explicitly state the restrictions that it is only for scientific equipment and consumables for research and only when not available on GeM. · error: the limit for scientific equipment and computers enhanced to Rs. 1,00,000 for each case |
| P-006 | ✓ | ✗ | ✗ | **no** | point 2 partial: The answer mentions the committee's responsibility for specifications and pricing but does not explicitly state the joint recording of a certificate as required by the reference point. · error: Additionally, a 'GeM Availability Report and Past Transaction Summary' (GeMAR&PTS) must be generated and submitted as a prerequisite for such procurement |
| P-007 | ✓ | ✗ | ✗ | yes | point 1 partial: The answer states Rs. 50 lakhs for 'other cases' but does not mention the exceptions in Rules 154, 155, 162, 166 as part of the core condition. · point 2 missing: The answer does not mention that the advertisement should be on GeM / GeM-CPPP. · error (quote not found, not counted): The estimated value of goods that must be procured through an advertised tender enquiry is Rs. 1,00,00,000/- (Rupees one crore) and above for Scientific Ministries/Departments/Organizations of Government of India |
| P-008 | ✓ | ✗ | ✗ | yes | point 1 partial: The answer states the value range as 'between Rs. 5 lakh to Rs. 50 lakhs', which is a specific case from the manual, but the reference point is the broader condition 'up to Rs 50 lakh' from GFR 2017. · error: A limited tender enquiry (LTE) may be used for goods when the estimated value of the procurement is between Rs. 5 lakh to Rs. 50 lakhs |
| P-009 | ✓ | ✓ | ✓ | **no** | point 2 partial: The answer mentions emergency but omits the requirement for recording reasons and obtaining competent authority approval. · point 3 partial: The answer mentions standardisation for compatibility but omits the requirement for advice from a competent technical expert and approval by the competent authority. |
| P-010 | ✓ | ✓ | ✓ | yes |  |
| P-011 | ✓ | ✓ | ✓ | yes | point 2 missing: The answer does not mention bidders registered with the Central Purchase Organisation or the concerned Ministry/Department as being exempt. |
| P-012 | ✓ | ✓ | ✓ | yes |  |
| P-013 | ✓ | ✓ | ✓ | yes |  |
| P-014 | ✓ | ✗ | ✗ | yes | point 2 missing: The answer does not mention the prohibition against splitting procurement to avoid the order. · error: The Make in India order applies to purchases with an estimated value of up to Rs 200 Crore, as stated in Rule 161(iv)(b) of GFR, 2017 |
| P-015 | ✓ | ✓ | ✓ | yes |  |
| P-016 | ✓ | ✓ | ✓ | yes |  |
| P-017 | ✓ | ✓ | ✓ | yes |  |
| P-018 | ✓ | ✗ | ✗ | yes | error: In case of inordinate delay, the maximum deduction can be increased to 10% of the total contract value |
| P-019 | ✓ | ✓ | ✓ | yes |  |
| P-020 | ✓ | ✓ | ✓ | yes |  |
| P-021 | ✗ | ✗ | ✗ | yes | point 1 partial: The answer states a specific 70/30 weighting, but the reference point indicates 80/20 for highly complex assignments, and the answer's cited source only mentions 70/30 as an example, not as the specific suggestion for highly complex cases. · point 2 missing: The answer does not mention the moderate complexity weighting range of 75-65 / 25-35 at all. · error: The manual suggests that for highly complex consultancy assignments, the quality-to-cost weighting should be 70% for quality and 30% for cost |
| P-022 | ✓ | ✗ | ✗ | yes | point 2 partial: The answer cites the correct OM date but incorrectly states the applicability date for the general registration requirement as after 01.04.2023, whereas the reference point does not specify an applicability date for this case. · error: This requirement applies to all procurements issued or published after 01.04.2023 |
| P-023 | ✗ | ✗ | ✗ | yes | point 1 missing: The answer states it cannot find the information, failing to address the reference point. |

Rows where the passes disagree need a person's verdict. Every judgement is in the JSON.
