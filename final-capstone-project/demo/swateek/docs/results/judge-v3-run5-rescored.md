# Content check: `e2e-v3-run5-rescored.json`

2026-11-13T12:42:29+00:00 · judge `deepseek-ai/DeepSeek-V3.2` (prompt v2) · 2 passes · system model `Qwen/Qwen3-8B` · eval v3

Rule: content correct = point 1 stated, no point contradicted, no material error with a verified quote; final = citation correct AND content correct (pass 1).

| Metric | Value |
|---|---|
| Citation correct (e2e scorer) | 22/23 |
| Content correct (judge) | 11/23 |
| **Final: citation and content correct** | **11/23** |
| Judge passes agree | 23/23 |
| Judge tokens (prompt / completion) | 74,722 / 7,008 |

| Id | Citation | Content | Final | Passes agree | Judge notes (pass 1) |
|---|---|---|---|---|---|
| P-001 | ✓ | ✗ | ✗ | yes | error: The rules for vendor screening and bid scoring in such scenarios are covered under the enabling provisions of Rule 149 of GFR 2017, which require the procuring authorities to certify the reasonability of rates. |
| P-002 | ✓ | ✓ | ✓ | yes | point 2 partial: The answer does not mention that online bidding or reverse auction tools may also be used, which is part of the reference point. |
| P-003 | ✓ | ✓ | ✓ | yes |  |
| P-004 | ✓ | ✗ | ✗ | yes | point 1 partial: The answer states the Rs. 50,000 limit for non-scientific ministries/departments but also introduces a different, higher limit for scientific ministries/departments, which is not part of the reference point. · error: purchases can be made without inviting quotations up to a value of Rs. 50,000/- for non-scientific ministries and departments [gfr_2017:R154], and up to Rs. 1,00,000/- for scientific ministries and departments [goods_manual_2024:4.12] · error: Additionally, for procurements above Rs. 50,000/- and up to Rs. 5,00,000/-, a Local Purchase Committee's recommendation is required [goods_manual_2024:4.13]. |
| P-005 | ✓ | ✗ | ✗ | yes | point 1 partial: The answer states the correct limit of Rs. 2 lakh for scientific departments but incorrectly restricts it to 'scientific equipment and computers' instead of the broader 'scientific equipment and consumables for research' as per the reference point. · error: Rs. 2,00,000/- (Rupees Two lakh) for scientific equipment and computers |
| P-006 | ✓ | ✗ | ✗ | yes | point 1 partial: The answer mentions that the process depends on specific rules and the nature of goods, but does not state the requirement for a Local Purchase Committee of three members. · point 2 missing: The answer does not mention the committee's market survey or the joint certificate recording. |
| P-007 | ✓ | ✗ | ✗ | yes | point 1 partial: The answer states Rs. 50 lakhs for 'other cases' but does not mention the exceptions (Rules 154, 155, 162, 166) that are part of the reference point. · point 2 missing: The answer does not mention that advertised tender enquiries should be advertised on GeM / GeM-CPPP. · error (quote not found, not counted): goods must be procured through an advertised tender enquiry if the estimated value is Rs. 1,00,00,000/- (Rupees one crore) and above for Scientific Ministries/Departments/Organizations of Government of India |
| P-008 | ✓ | ✗ | ✗ | yes | point 2 missing: The answer does not mention that bidding documents are sent directly to registered suppliers. · error: LTE is the default mode for procurements below a certain threshold, typically up to Rs. 10 lakhs |
| P-009 | ✓ | ✗ | ✗ | yes | point 2 partial: The answer mentions emergency but omits the requirement for recording reasons and obtaining competent authority approval. · error: single-source procurement may be resorted to if the procurement entity engages in activities related to national defence or national security · error: single-source procurement may be resorted to if there are special circumstances where selecting a particular consultant is necessary for the overall interest of the Ministry or Department |
| P-010 | ✓ | ✓ | ✓ | yes |  |
| P-011 | ✓ | ✗ | ✗ | yes | point 2 missing: The answer does not mention bidders registered with the Central Purchase Organisation or the concerned Ministry/Department. · error: Additionally, bidders in indigenisation/development tenders, limited tenders, and procurements directly from the manufacturer or authorised agents may be exempt with the Competent Authority’s approval |
| P-012 | ✓ | ✓ | ✓ | yes |  |
| P-013 | ✓ | ✗ | ✗ | yes | point 1 contradicted: The answer states splitting is permissible under certain conditions, but the reference point explicitly prohibits splitting to avoid higher authority sanction. · error: splitting a requirement into smaller orders is permissible if it aligns with the procurement guidelines and does not violate any specific thresholds or conditions |
| P-014 | ✓ | ✓ | ✓ | yes | point 2 missing: The answer does not mention the prohibition against splitting procurement to avoid the Order. |
| P-015 | ✓ | ✓ | ✓ | yes |  |
| P-016 | ✓ | ✓ | ✓ | yes |  |
| P-017 | ✓ | ✓ | ✓ | yes |  |
| P-018 | ✓ | ✗ | ✗ | yes | error: In case of inordinate delay, the maximum deduction can be increased to 10% of the total contract value |
| P-019 | ✓ | ✓ | ✓ | yes |  |
| P-020 | ✓ | ✓ | ✓ | yes |  |
| P-021 | ✗ | ✗ | ✗ | yes | point 1 partial: The answer states a typical 70/30 weighting but does not mention the 80/20 weighting specifically suggested for highly complex assignments. · point 2 missing: The answer does not address the moderate complexity weighting range of 75-65/25-35. · error: the technical (quality) score is given a weightage of 70% while the cost score is given 30% |
| P-022 | ✓ | ✗ | ✗ | yes | point 2 partial: The answer cites the correct OM date but incorrectly states the applicability date for the general registration requirement as after 01.04.2023, whereas the reference point does not specify an applicability date for this case. · error: This requirement applies to all procurements issued or published after 01.04.2023. |
| P-023 | ✓ | ✓ | ✓ | yes |  |

Rows where the passes disagree need a person's verdict. Every judgement is in the JSON.
