# Content check: `e2e-v2-run3.json`

2026-11-13T09:36:45+00:00 · judge `deepseek-ai/DeepSeek-V3.2` (prompt v2) · 2 passes · system model `Qwen/Qwen3-8B` · eval v2

Rule: content correct = point 1 stated, no point contradicted, no material error with a verified quote; final = citation correct AND content correct (pass 1).

| Metric | Value |
|---|---|
| Citation correct (e2e scorer) | 21/23 |
| Content correct (judge) | 14/23 |
| **Final: citation and content correct** | **14/23** |
| Judge passes agree | 22/23 |
| Judge tokens (prompt / completion) | 72,026 / 6,834 |

| Id | Citation | Content | Final | Passes agree | Judge notes (pass 1) |
|---|---|---|---|---|---|
| P-001 | ✓ | ✓ | ✓ | yes |  |
| P-002 | ✓ | ✓ | ✓ | yes |  |
| P-003 | ✓ | ✓ | ✓ | yes |  |
| P-004 | ✓ | ✗ | ✗ | yes | point 1 partial: The answer states the general threshold of Rs. 50,000 but also introduces a higher threshold of Rs. 1,00,000 for a specific case (Scientific Ministries/Departments), which is not part of the reference point's core content. · point 2 partial: The answer mentions obtaining a certificate from the competent authority confirming quality and specification, but omits the required format and the specific conditions of 'from a reliable supplier at a reasonable price'. · error: for Scientific Ministries/Departments, it is enhanced to Rs. 1,00,000/- for scientific equipment and computers · error: Additionally, for procurements above Rs. 50,000/- and up to Rs. 5,00,000/-, a Local Purchase Committee's recommendation is required |
| P-005 | ✓ | ✗ | ✗ | yes | point 1 partial: The answer states a limit of Rs. 2,00,000/- for scientific departments, but incorrectly attributes it to 'procurement outside GeM' and does not specify it is for 'notified scientific Ministries/Departments/organisations' as per the reference point. · point 2 partial: The answer mentions the limit is for procurement outside GeM, which aligns with 'only when not available on GeM', but does not state the restriction to 'scientific equipment and consumables for research'. · error: The limit for purchase without quotation for scientific departments like DRDO or ICAR has been enhanced to Rs. 1,00,000/- for each case |
| P-006 | ✓ | ✓ | ✓ | yes | point 2 partial: The answer mentions the committee surveys the market but omits the requirement for the members to jointly record a certificate. |
| P-007 | ✓ | ✗ | ✗ | yes | point 1 partial: The answer states Rs. 50 lakhs and above for 'other cases' but does not mention the exceptions in Rules 154, 155, 162, 166 as part of the core condition. · point 2 partial: The answer mentions advertisement on GeM/GeM-CPPP for 'other cases' but does not state it as a general requirement for the Rs. 50 lakh threshold. · error (quote not found, not counted): The estimated value of goods that must be procured through an advertised tender enquiry is Rs. 1,00,00,000/- (Rupees one crore) and above for Scientific Ministries/Departments/Organizations of Government of India |
| P-008 | ✓ | ✓ | ✓ | yes | point 2 partial: The answer mentions a preselected panel of registered suppliers but does not explicitly state that bidding documents are sent directly to them. |
| P-009 | ✓ | ✓ | ✓ | yes | point 2 partial: The answer mentions emergency but omits the requirement for recording reasons and obtaining competent authority approval. · point 3 partial: The answer mentions standardisation for compatibility but adds the condition of technical expert advice and competent authority approval, which are not part of the reference point's core content. |
| P-010 | ✓ | ✓ | ✓ | yes |  |
| P-011 | ✓ | ✓ | ✓ | yes |  |
| P-012 | ✓ | ✓ | ✓ | yes |  |
| P-013 | ✓ | ✗ | ✗ | yes | point 1 contradicted: The answer states that splitting is permissible, but the reference point explicitly prohibits dividing a demand to avoid higher sanction. · error: there is no explicit restriction on splitting a requirement into smaller orders for sanctioning purposes · error: splitting a Rs 12 lakh requirement into four smaller orders is permissible under these guidelines |
| P-014 | ✓ | ✗ | ✗ | yes | point 1 contradicted: The answer states the order applies to a Rs 4 lakh purchase, but the reference point says such procurements are exempt. · error: The Make in India order applies to purchases estimated at Rs 4 lakh |
| P-015 | ✓ | ✓ | ✓ | yes |  |
| P-016 | ✓ | ✓ | ✓ | yes |  |
| P-017 | ✓ | ✓ | ✓ | yes |  |
| P-018 | ✓ | ✗ | ✗ | yes | error: The quantum of liquidated damages is also influenced by variations in the contract and the nature of the delay [ncs_manual_2025:9.4.7]. |
| P-019 | ✓ | ✓ | ✓ | yes |  |
| P-020 | ✓ | ✓ | ✓ | yes |  |
| P-021 | ✗ | ✗ | ✗ | yes | point 1 partial: The answer states a typical 70/30 ratio and mentions an 80% maximum, but does not clearly state the 80/20 ratio suggested for highly complex assignments. · point 2 missing: The answer does not address the moderate complexity weighting range of 75-65 / 25-35. · error: The manual suggests that for highly complex consultancy assignments, the quality-to-cost weighting under QCBS is typically 70% for quality and 30% for cost |
| P-022 | ✓ | ✗ | ✗ | **no** | point 2 partial: The answer correctly cites the DoE OM but provides an incorrect applicability date (01.04.2023) for the general registration requirement, which the source indicates has been applicable since 23.07.2020. · error: This requirement applies to all procurements issued or published after 01.04.2023 |
| P-023 | ✗ | ✗ | ✗ | yes | point 1 contradicted: The answer incorrectly states the evaluation sheet is a 'draft score sheet for the evaluation committee, which is not an award', contradicting the reference point that it is the sheet stored with the case. · error: The evaluation sheet used for scoring the bid case is the draft score sheet for the evaluation committee, which is not an award. |

Rows where the passes disagree need a person's verdict. Every judgement is in the JSON.
