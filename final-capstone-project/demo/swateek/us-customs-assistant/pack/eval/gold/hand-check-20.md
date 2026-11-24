# Hand-check: 20 gold answers (plan step 5)

Extracted from `workings.md` (built independently by `build_gold.py`). For each entry, check the exemption, the allocation, every duty and excise line, the total, the outcome, and the cited rules against `docs/regulatory-checks.md`. Disagreements are settled against the regulation text before `eval-v1` is frozen.

Cross-check by the main session, recomputed independently (all equal to the cent): A01 $3.23, A04 $1.62, A10 $3.65, C01 $2.14, G04 $6.70, G08 $4.72, G10 $1.49, I06 $0.42.

| Entry | Your check (OK / issue) |
|---|---|
| A01 | OK (figures, outcome, notes). Citation F1 resolved: R11 no longer required on a single line |
| A04 | OK: gin fills the 1 L first (R11, 148.33(b)); 1.5 L wine dutiable, $1.62 |
| A07 | OK: Mexico arrival gets $800 regardless of hours (148.35(a)); 750 ml within 1 L; no clarify (state never asked alone) |
| A10 | OK (figures, outcome, USMCA duty 0 with caveat). Citation F1 resolved: R11 no longer required on a single line |
| B01 | OK: direct from Jamaica, 2 L of Jamaican rum, all exempt (148.33(d)(3)(ii)) |
| B03 | OK: 2 L via Decision A (DR on CBP's list); cognac allocated first; 250 ml DR rum dutiable, CAFTA-DR duty 0, excise $0.71 |
| C01 | OK: under 48 h from Canada, so $200; 750 ml > 150 ml, nothing exempt (148.51(b)); excise $2.14, USMCA duty 0 |
| C05 | OK: Decision A1 confirmed by the user (all 40 cigarettes at seizure risk); wine excise $0.11 |
| C08 | OK: exemption used 10 days ago, so $200 (148.36(a)); whole bottle dutiable, $2.14; CA flag |
| D01 | OK: turn 1 asks age + 30-day only (no alcohol, so no state); turn 2: 200 exempt, 200 at seizure risk (R5) |
| D02 | OK: 600 US export-labelled; 200 within the allowance; 400 excess; R5 + R6 notes (26 USC 5761(c)-(d)) |
| E04 | OK: Decision E; asks origin once; unknown, so possibly Cuban, no allowance, declare; R12 + R4 third country |
| F01 | OK: 19, no alcohol allowance (148.33(d)(2)); duty $0.60 + excise $0.21 = $0.81 |
| G02 | OK: grappa first, then 300 ml wine; 1,950 ml wine dutiable, $2.50; tobacco within the allowance |
| G04 | OK: whiskey first; 1 L whiskey + 7.92 L beer dutiable, $6.70; IL flag (see F2) |
| G07 | OK: 13 L > 12 L flag (Decision D), so escalated; R10 only |
| G08 | OK: gin first; 1 L gin + 1.5 L wine dutiable, $4.72; 50 cigars within the allowance |
| G10 | OK: schnapps, then 300 ml riesling exempt; 450 ml riesling + 3 L beer dutiable, $1.49 |
| I02 | OK: asks age, 30-day and state (bundled); reply gives $800 (Mexico), 750 ml within 1 L, CA flag |
| I06 | OK: asks 30-day + state; reply says used, so $200; 1.5 L Canadian wine dutiable, USMCA duty 0, excise $0.42 |


## Review (2026-11-17)

**Reviewer.** The main Claude session, at the user's request, in place of the user's own hand-check (plan step 5). The gold was built by a separate agent with no access to app code; this review is a second, separate computation.

**Method.**
1. Recomputed every figure of all 20 entries with a separate script written for this review (SPEC §5 order; Decimal; per-line half-up rounding to the cent): exemption, allowance, allocation order, per-line exempt and dutiable ml, pro-rata dutiable value, duty rate, duty, excise, sticks and totals. **All figures match the gold** (19 answered entries line by line; G07 checked as an escalation at 13 L).
2. Checked that every cited clause id exists in the corpus (`data/chunks/documents.jsonl`): **all exist**.
3. Read each scenario's text against its `facts`: **all agree**.
4. Checked each outcome, clarify field set, citation and required note against the signed-off rules, the decisions A–G and the regulation text quoted in `docs/regulatory-checks.md`:
   - 148.33(b), (d); 148.35(a); 148.36(a)–(b); 148.51(b);
   - 9804.00.65 and .72; 9816.00.20;
   - GN 3(c) and 11(a);
   - 26 USC 5001(a), 5041(b), 5051(a), 5761(c)–(d);
   - 31 CFR 515.204(a), 515.585(d);
   - TTB rate tables; CBP tobacco and alcohol guidance.

**Findings.**
- **F1 (citations, cross-cutting).** Rule R11 ("fill the allowance with the highest duty + tax first", 19 CFR 148.33(b)) is a required citation on **37 answered turns where only one alcohol line exists**, so nothing is being allocated. Among the 20 this affects A01 and A10. Requiring 148.33(b) there would mark a correct, well-cited answer as missing a citation. **Recommendation:** require R11 only when two or more admissible alcohol lines compete for the allowance; keep it optional otherwise. This changes citation claims only; no figure or outcome changes. Needs a gold rebuild by the gold builder (judgement policy A6).
- **F2 (evidence gap, state flag).** The Illinois flag (`states.yaml`: "personal imports need ILCC authorisation and Illinois Use Tax") rests on the ILCC import form only. The Illinois rule itself (11 Ill. Adm. Code 100.480, which reportedly lets an individual import under 1 gallon a year without a licence) could not be fetched (ilga.gov unreachable). For G04 (9.92 L, about 2.6 gallons) the flag is consistent either way. For small quantities the flag may overstate. No gold change; noted for the report and for a re-fetch of ilga.gov.
- E04's figures differ from a naive computation only because the gold correctly applies Decision E (no allowance for an ambiguous brand with unknown origin). Not a finding.

**Result.** 20 of 20 OK on figures and outcomes. F1 should be resolved (citation policy) before freezing `eval-v1`; F2 is a documented limitation.

**F1 resolved (2026-11-17).** Approved by the user. The gold builder changed policy A6: R11 is required only when two or more admissible alcohol lines compete for the allowance. It rebuilt the gold. The main session diffed the previous and new `gold.jsonl` independently: exactly **37 turns** changed, each by **one removed R11 claim**; no outcome, figure, note, clarify field, other citation or workings text changed. The workings copied below are as reviewed, so the "Cite R11" line in the single-line entries (e.g. A01, A10) no longer applies.

---

### A01 (alcohol_excess_800)

**HAND-CHECK**

> T1: I'm 41, back from a week in France and this is my first trip abroad this year. I have two 750 ml bottles of cognac (40%) that cost $90 each. What do I owe?

**Turn 1: answered** (owe, owe $3.23). You'll owe about $3.23.

- Exemption $800 (R9): trip 168 h >= 48 h; not used in the last 30 days.
- Alcohol allowance 1000 ml.
- Line 1 spirits 1500 ml @ 40%: exempt 1000 ml, dutiable 500 ml.
- Line 1 duty: value $180 x 500/1500 = $60.0000; 3% flat rate -> $1.80. Excise (distilled_spirits, $13.5/proof_gallon): 0.132086 gal x proof 80/100 = 0.105669 pg -> $1.426529 -> $1.43.
- Totals: duty $1.80 + excise $1.43 = $3.23.
- Figures: `exemption_usd`=800, `alcohol_allowance_ml`=1000, `exempt_ml_1`=1000, `dutiable_ml_1`=500, `dutiable_value_usd_1`=60.00, `duty_rate_1`=0.03, `duty_usd_1`=1.80, `excise_usd_1`=1.43, `duty_total_usd`=1.80, `excise_total_usd`=1.43, `total_owed_usd`=3.23
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R11 allocate_exemption_to_highest_cost: any of `cfr19_p148:148.33(b)`
- Cite R7 flat_rate_duty: any of `hts_9816_rows:9816.00.20`, `cfr19_p148:148.101`, `cfr19_p148:148.102(a)`, `hts_general_notes:general-note-3-b`, `hts_general_notes:general-note-3-c`, `hts_general_notes:general-note-11-a`, `cbp_customs_duty_info:determining-customs-duty`
- Cite R8 excise_general_rates: any of `ttb_tax_rates:alcohol-tax-rates-for-calendar-years-2018-to-pre`, `usc26_5001:5001(a)`, `usc26_5041:5041(b)`, `usc26_5051:5051(a)`, `cfr27_p27:27.45`
- Notes required: disclaimer, generic_state_note

### A04 (alcohol_excess_800)

**HAND-CHECK**

> T1: Back from 10 days in Spain. I'm 37, no other trips recently. I'm carrying two 750 ml bottles of Rioja at $20 each and one 1 liter bottle of Spanish gin (40%) that cost $35. What will customs charge?

**Turn 1: answered** (owe, owe $1.62). You'll owe about $1.62.

- Line 1: ABV not stated: 12.5% default for wine (units.yaml).
- Exemption $800 (R9): trip 240 h >= 48 h; not used in the last 30 days.
- Alcohol allowance 1000 ml.
- R11 ranking (3% of value per litre + excise per litre): line 2 spirits $3.9031/L; line 1 wine $1.0827/L
- Line 1 wine 1500 ml @ 12.5%: exempt 0 ml, dutiable 1500 ml.
- Line 2 spirits 1000 ml @ 40%: exempt 1000 ml, dutiable 0 ml.
- Line 1 duty: value $40 x 1500/1500 = $40.0000; 3% flat rate -> $1.20. Excise (still_wine_le_16, $1.07/wine_gallon): 0.396258 wine gal -> $0.423996 -> $0.42.
- Totals: duty $1.20 + excise $0.42 = $1.62.
- Figures: `exemption_usd`=800, `alcohol_allowance_ml`=1000, `exempt_ml_1`=0, `dutiable_ml_1`=1500, `dutiable_value_usd_1`=40.00, `duty_rate_1`=0.03, `duty_usd_1`=1.20, `excise_usd_1`=0.42, `exempt_ml_2`=1000, `dutiable_ml_2`=0, `duty_total_usd`=1.20, `excise_total_usd`=0.42, `total_owed_usd`=1.62
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R11 allocate_exemption_to_highest_cost: any of `cfr19_p148:148.33(b)`
- Cite R7 flat_rate_duty: any of `hts_9816_rows:9816.00.20`, `cfr19_p148:148.101`, `cfr19_p148:148.102(a)`, `hts_general_notes:general-note-3-b`, `hts_general_notes:general-note-3-c`, `hts_general_notes:general-note-11-a`, `cbp_customs_duty_info:determining-customs-duty`
- Cite R8 excise_general_rates: any of `ttb_tax_rates:alcohol-tax-rates-for-calendar-years-2018-to-pre`, `usc26_5001:5001(a)`, `usc26_5041:5041(b)`, `usc26_5051:5051(a)`, `cfr27_p27:27.45`
- Notes required: disclaimer, generic_state_note

### A07 (alcohol_excess_800)

**HAND-CHECK**

> T1: Day trip to Tijuana. I'm 30, haven't used my exemption in the last 30 days, and I bought one 750 ml bottle of tequila for $35. Do I owe anything?

*Judgement:* Mexico arrival: $800 regardless of time away (R9); 750 ml fits the 1 L allowance.

**Turn 1: answered** (nothing_owed, owe $0.00). You owe nothing: it is all within your exemption.

- Line 1: ABV not stated: 40% default for spirits (units.yaml).
- Exemption $800 (R9): arrived directly from Mexico (no 48-hour minimum); not used in the last 30 days.
- Alcohol allowance 1000 ml.
- Line 1 spirits 750 ml @ 40%: exempt 750 ml, dutiable 0 ml.
- Figures: `exemption_usd`=800, `alcohol_allowance_ml`=1000, `exempt_ml_1`=750, `dutiable_ml_1`=0
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Notes required: disclaimer, generic_state_note

### A10 (alcohol_excess_800)

**HAND-CHECK**

> T1: Driving back from 4 days in Toronto. I'm 39 and haven't claimed an exemption in the past month. I have two 1.14 liter bottles of Canadian whisky (40%) at $45 each. What do I pay?

**Turn 1: answered** (owe, owe $3.65). You'll owe about $3.65.

- Exemption $800 (R9): trip 96 h >= 48 h; not used in the last 30 days.
- Alcohol allowance 1000 ml.
- Line 1 spirits 2280 ml @ 40%: exempt 1000 ml, dutiable 1280 ml.
- Line 1 duty: value $90 x 1280/2280 = $50.5263; free: product of USMCA (S) partner, if it qualifies as originating -> $0.00. Excise (distilled_spirits, $13.5/proof_gallon): 0.338140 gal x proof 80/100 = 0.270512 pg -> $3.651914 -> $3.65.
- Totals: duty $0.00 + excise $3.65 = $3.65.
- Figures: `exemption_usd`=800, `alcohol_allowance_ml`=1000, `exempt_ml_1`=1000, `dutiable_ml_1`=1280, `dutiable_value_usd_1`=50.53, `duty_rate_1`=0, `duty_usd_1`=0.00, `excise_usd_1`=3.65, `duty_total_usd`=0.00, `excise_total_usd`=3.65, `total_owed_usd`=3.65
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R11 allocate_exemption_to_highest_cost: any of `cfr19_p148:148.33(b)`
- Cite R7 flat_rate_duty: any of `hts_9816_rows:9816.00.20`, `cfr19_p148:148.101`, `cfr19_p148:148.102(a)`, `hts_general_notes:general-note-3-b`, `hts_general_notes:general-note-3-c`, `hts_general_notes:general-note-11-a`, `cbp_customs_duty_info:determining-customs-duty`
- Cite R8 excise_general_rates: any of `ttb_tax_rates:alcohol-tax-rates-for-calendar-years-2018-to-pre`, `usc26_5001:5001(a)`, `usc26_5041:5041(b)`, `usc26_5051:5051(a)`, `cfr27_p27:27.45`
- Notes required: disclaimer, generic_state_note, fta_caveat

### B01 (alcohol_cbi_2L)

**HAND-CHECK**

> T1: Flying straight home from Montego Bay after 7 days. I'm 44 and haven't used my exemption this month. I have two 1 liter bottles of Jamaican rum (40%), $25 each. Do I owe anything?

**Turn 1: answered** (nothing_owed, owe $0.00). You owe nothing: it is all within your exemption.

- Exemption $800 (R9): trip 168 h >= 48 h; not used in the last 30 days.
- Arrived directly from JM (CBP Caribbean Basin list, Decision A) and 2000 ml is a beneficiary-country product (>= 1 L): 2 L allowance (R2).
- Alcohol allowance 2000 ml.
- Line 1 spirits 2000 ml @ 40%: exempt 2000 ml, dutiable 0 ml.
- Figures: `exemption_usd`=800, `alcohol_allowance_ml`=2000, `exempt_ml_1`=2000, `dutiable_ml_1`=0
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R2 caribbean_basin_two_litres: any of `cfr19_p148:148.33(d)`, `hts_9804_rows:9804.00.72`, `hts_ch98_pdf:subchapter-iv-u-s-note-4`, `hts_general_notes:general-note-7-a`, `cbp_types_exemptions:overview`
- Notes required: disclaimer, generic_state_note

### B03 (alcohol_cbi_2L)

**HAND-CHECK**

> T1: Flying direct from Punta Cana after a week. I'm 50, no exemption used lately. I have two 750 ml bottles of Dominican rum ($28 each, 40%) and one 750 ml bottle of French cognac ($70, 40%) from the duty-free there. What do I owe?

**Turn 1: answered** (owe, owe $0.71). You'll owe about $0.71.

- Exemption $800 (R9): trip 168 h >= 48 h; not used in the last 30 days.
- Arrived directly from DO (CBP Caribbean Basin list, Decision A) and 1500 ml is a beneficiary-country product (>= 1 L): 2 L allowance (R2).
- Alcohol allowance 2000 ml.
- R11 ranking (3% of value per litre + excise per litre): line 2 spirits $5.6531/L; line 1 spirits $3.9731/L
- Line 1 spirits 1500 ml @ 40%: exempt 1250 ml, dutiable 250 ml.
- Line 2 spirits 750 ml @ 40%: exempt 750 ml, dutiable 0 ml.
- Line 1 duty: value $56 x 250/1500 = $9.3333; free: product of CAFTA-DR (P) partner, if it qualifies as originating -> $0.00. Excise (distilled_spirits, $13.5/proof_gallon): 0.066043 gal x proof 80/100 = 0.052834 pg -> $0.713265 -> $0.71.
- Totals: duty $0.00 + excise $0.71 = $0.71.
- Figures: `exemption_usd`=800, `alcohol_allowance_ml`=2000, `exempt_ml_1`=1250, `dutiable_ml_1`=250, `dutiable_value_usd_1`=9.33, `duty_rate_1`=0, `duty_usd_1`=0.00, `excise_usd_1`=0.71, `exempt_ml_2`=750, `dutiable_ml_2`=0, `duty_total_usd`=0.00, `excise_total_usd`=0.71, `total_owed_usd`=0.71
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R2 caribbean_basin_two_litres: any of `cfr19_p148:148.33(d)`, `hts_9804_rows:9804.00.72`, `hts_ch98_pdf:subchapter-iv-u-s-note-4`, `hts_general_notes:general-note-7-a`, `cbp_types_exemptions:overview`
- Cite R11 allocate_exemption_to_highest_cost: any of `cfr19_p148:148.33(b)`
- Cite R7 flat_rate_duty: any of `hts_9816_rows:9816.00.20`, `cfr19_p148:148.101`, `cfr19_p148:148.102(a)`, `hts_general_notes:general-note-3-b`, `hts_general_notes:general-note-3-c`, `hts_general_notes:general-note-11-a`, `cbp_customs_duty_info:determining-customs-duty`
- Cite R8 excise_general_rates: any of `ttb_tax_rates:alcohol-tax-rates-for-calendar-years-2018-to-pre`, `usc26_5001:5001(a)`, `usc26_5041:5041(b)`, `usc26_5051:5051(a)`, `cfr27_p27:27.45`
- Notes required: disclaimer, generic_state_note, fta_caveat

### C01 (exemption_200_all_or_nothing)

**HAND-CHECK**

> T1: Day trip to Niagara Falls, Ontario, about 10 hours. I'm 28 and haven't used an exemption this month. I bought one 750 ml bottle of Canadian whisky, 40%, for $30. What do I owe?

**Turn 1: answered** (owe, owe $2.14). You'll owe about $2.14.

- Exemption $200 (R9 -> R1): trip 10 h < 48 h and not arriving from Mexico.
- R1 all-or-nothing triggered (750 ml alcohol > 150 ml): NOTHING is exempt.
- Line 1 spirits 750 ml @ 40%: exempt 0 ml, dutiable 750 ml.
- Line 1 duty: value $30 x 750/750 = $30.0000; free: product of USMCA (S) partner, if it qualifies as originating -> $0.00. Excise (distilled_spirits, $13.5/proof_gallon): 0.198129 gal x proof 80/100 = 0.158503 pg -> $2.139794 -> $2.14.
- Totals: duty $0.00 + excise $2.14 = $2.14.
- Figures: `exemption_usd`=200, `alcohol_allowance_ml`=150, `exempt_ml_1`=0, `dutiable_ml_1`=750, `dutiable_value_usd_1`=30.00, `duty_rate_1`=0, `duty_usd_1`=0.00, `excise_usd_1`=2.14, `duty_total_usd`=0.00, `excise_total_usd`=2.14, `total_owed_usd`=2.14
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R1 exemption_200_all_or_nothing: any of `cfr19_p148:148.51(a)`, `cfr19_p148:148.51(b)`, `cfr19_p148:148.51(c)`, `cbp_types_exemptions:overview`
- Cite R7 flat_rate_duty: any of `hts_9816_rows:9816.00.20`, `cfr19_p148:148.101`, `cfr19_p148:148.102(a)`, `hts_general_notes:general-note-3-b`, `hts_general_notes:general-note-3-c`, `hts_general_notes:general-note-11-a`, `cbp_customs_duty_info:determining-customs-duty`
- Cite R8 excise_general_rates: any of `ttb_tax_rates:alcohol-tax-rates-for-calendar-years-2018-to-pre`, `usc26_5001:5001(a)`, `usc26_5041:5041(b)`, `usc26_5051:5051(a)`, `cfr27_p27:27.45`
- Notes required: disclaimer, generic_state_note, fta_caveat

### C05 (exemption_200_all_or_nothing)

**HAND-CHECK**

> T1: Day trip to Vancouver. I'm 33, no exemption used in the last 30 days. I bought 2 packs of cigarettes (40 total, $24) and a 375 ml half bottle of Canadian wine (12%, $15). What happens at customs?

*Judgement:* 375 ml > 150 ml breaks the $200 all-or-nothing: nothing is exempt, so all 40 cigarettes are outside any exemption (seizure risk, R5) and the wine is dutiable.

**Turn 1: answered** (mixed, owe $0.11). You'll owe about $0.11. 40 cigarettes are over the allowance and may be detained or seized; declare them.

- Exemption $200 (R9 -> R1): trip under 48 h and not arriving from Mexico.
- R1 all-or-nothing triggered (375 ml alcohol > 150 ml): NOTHING is exempt.
- Line 2 wine 375 ml @ 12%: exempt 0 ml, dutiable 375 ml.
- Line 1 cigarettes 40: exempt 0, over the allowance 40 -> seizure risk, not taxed (R5).
- Line 2 duty: value $15 x 375/375 = $15.0000; free: product of USMCA (S) partner, if it qualifies as originating -> $0.00. Excise (still_wine_le_16, $1.07/wine_gallon): 0.099065 wine gal -> $0.105999 -> $0.11.
- Totals: duty $0.00 + excise $0.11 = $0.11.
- Figures: `exemption_usd`=200, `alcohol_allowance_ml`=150, `exempt_sticks_1`=0, `excess_sticks_1`=40, `exempt_ml_2`=0, `dutiable_ml_2`=375, `dutiable_value_usd_2`=15.00, `duty_rate_2`=0, `duty_usd_2`=0.00, `excise_usd_2`=0.11, `duty_total_usd`=0.00, `excise_total_usd`=0.11, `total_owed_usd`=0.11
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R1 exemption_200_all_or_nothing: any of `cfr19_p148:148.51(a)`, `cfr19_p148:148.51(b)`, `cfr19_p148:148.51(c)`, `cbp_types_exemptions:overview`
- Cite R5 tobacco_over_allowance: any of `cbp_customs_duty_info:tobacco-products`, `cfr19_p148:148.33(d)`, `cfr27_p41:41.190`
- Cite R7 flat_rate_duty: any of `hts_9816_rows:9816.00.20`, `cfr19_p148:148.101`, `cfr19_p148:148.102(a)`, `hts_general_notes:general-note-3-b`, `hts_general_notes:general-note-3-c`, `hts_general_notes:general-note-11-a`, `cbp_customs_duty_info:determining-customs-duty`
- Cite R8 excise_general_rates: any of `ttb_tax_rates:alcohol-tax-rates-for-calendar-years-2018-to-pre`, `usc26_5001:5001(a)`, `usc26_5041:5041(b)`, `usc26_5051:5051(a)`, `cfr27_p27:27.45`
- Notes required: disclaimer, generic_state_note, fta_caveat, seizure_risk

### C08 (exemption_200_all_or_nothing)

**HAND-CHECK**

> T1: Walking back across from Tijuana to San Diego today. I live in California, I'm 31, and I already used my duty-free exemption on a Tijuana trip 10 days ago. Today I bought one 750 ml bottle of Mexican tequila, 40%, for $35. What do I owe?

**Turn 1: answered** (owe, owe $2.14). You'll owe about $2.14.

- Exemption $200 (R9 -> R1): the $800 exemption was used in the last 30 days.
- R1 all-or-nothing triggered (750 ml alcohol > 150 ml): NOTHING is exempt.
- Line 1 spirits 750 ml @ 40%: exempt 0 ml, dutiable 750 ml.
- Line 1 duty: value $35 x 750/750 = $35.0000; free: product of USMCA (S) partner, if it qualifies as originating -> $0.00. Excise (distilled_spirits, $13.5/proof_gallon): 0.198129 gal x proof 80/100 = 0.158503 pg -> $2.139794 -> $2.14.
- Totals: duty $0.00 + excise $2.14 = $2.14.
- Figures: `exemption_usd`=200, `alcohol_allowance_ml`=150, `exempt_ml_1`=0, `dutiable_ml_1`=750, `dutiable_value_usd_1`=35.00, `duty_rate_1`=0, `duty_usd_1`=0.00, `excise_usd_1`=2.14, `duty_total_usd`=0.00, `excise_total_usd`=2.14, `total_owed_usd`=2.14
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R1 exemption_200_all_or_nothing: any of `cfr19_p148:148.51(a)`, `cfr19_p148:148.51(b)`, `cfr19_p148:148.51(c)`, `cbp_types_exemptions:overview`
- Cite R7 flat_rate_duty: any of `hts_9816_rows:9816.00.20`, `cfr19_p148:148.101`, `cfr19_p148:148.102(a)`, `hts_general_notes:general-note-3-b`, `hts_general_notes:general-note-3-c`, `hts_general_notes:general-note-11-a`, `cbp_customs_duty_info:determining-customs-duty`
- Cite R8 excise_general_rates: any of `ttb_tax_rates:alcohol-tax-rates-for-calendar-years-2018-to-pre`, `usc26_5001:5001(a)`, `usc26_5041:5041(b)`, `usc26_5051:5051(a)`, `cfr27_p27:27.45`
- Cite CA arrival-state flag: any of `state_ca:travel-by-steamship-or-airplane`, `state_ca:returning-from-mexico`
- Notes required: disclaimer, state_flag:CA, fta_caveat

### D01 (tobacco_over_limit)

**HAND-CHECK**

> T1: Flying home from Dubai after two weeks. I bought two cartons of cigarettes (400) at duty-free.
> T2: I'm 41, and no, I haven't used my exemption in the last 30 days.

**Turn 1: clarify** (clarify). Are you 21 or older, and have you used your duty-free exemption in the last 30 days?

- Clarify fields: age_21_plus, exemption_used_last_30_days
- Clarify: missing answer-changing facts -> age_21_plus, exemption_used_last_30_days.

**Turn 2: answered** (seizure_risk, owe $0.00). You owe nothing on what you can bring in. 200 cigarettes are over the allowance and may be detained or seized; declare them.

- Exemption $800 (R9): trip >=48 h; not used in the last 30 days.
- Line 1 cigarettes 400: exempt 200, over the allowance 200 -> seizure risk, not taxed (R5).
- Figures: `exemption_usd`=800, `exempt_sticks_1`=200, `excess_sticks_1`=200
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R5 tobacco_over_allowance: any of `cbp_customs_duty_info:tobacco-products`, `cfr19_p148:148.33(d)`, `cfr27_p41:41.190`
- Notes required: disclaimer, seizure_risk

### D02 (tobacco_over_limit)

**HAND-CHECK**

> T1: Back from 8 days in Germany. I'm 55, first trip this year. At Frankfurt duty-free I bought three cartons of Marlboro made in the US, labelled 'Tax exempt, for use outside the US'. What happens with those?

**Turn 1: answered** (seizure_risk, owe $0.00). You owe nothing on what you can bring in. 400 cigarettes are over the allowance and may be detained or seized; declare them.

- Exemption $800 (R9): trip 192 h >= 48 h; not used in the last 30 days.
- Line 1 cigarettes 600: exempt 200, over the allowance 400 -> seizure risk, not taxed (R5) [US export-labelled: R6 relinquish note].
- Figures: `exemption_usd`=800, `exempt_sticks_1`=200, `excess_sticks_1`=400
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R5 tobacco_over_allowance: any of `cbp_customs_duty_info:tobacco-products`, `cfr19_p148:148.33(d)`, `cfr27_p41:41.190`
- Cite R6 us_export_labelled_tobacco: any of `usc26_5754:5754(a)`, `usc26_5761:5761(c)`, `usc26_5761:5761(d)`
- Notes required: disclaimer, seizure_risk, us_export_labelled_relinquish

### E04 (cuban_origin)

**HAND-CHECK**

> T1: Flying home from Punta Cana after a week. I'm 39, haven't used my exemption this month. I bought 6 Cohibas at a shop in the resort. Fine to bring?
> T2: Honestly I'm not sure where they were made.

*Judgement:* Origin still unknown after the one question: Decision E, treat as possibly Cuban, no allowance, declare.

**Turn 1: clarify** (clarify). Were the Cohibas made in Cuba?

- Clarify fields: origin_country_of_line
- Clarify: missing answer-changing facts -> origin_country_of_line.

**Turn 2: answered** (prohibited, owe $0.00). Treat them as possibly Cuban: no allowance applies; declare them and let the officer decide.

- Line 1 (cigars, brand Cohiba): origin still unknown after one question -> treated as possibly Cuban: no allowance, declare (R12, Decision E).
- Cite R12 origin_not_from_brand: any of `cfr31_p515:515.204(a)`
- Cite R4 Cuban-origin alcohol/tobacco bought in a third country is prohibited: any of `cfr31_p515:515.204(a)`, `cfr31_p515:515.585(c)`, `cfr31_p515:515.585(d)`, `ofac_cuba_faqs:faq-720`
- Notes required: disclaimer, possibly_cuban_declare

### F01 (under_21)

**HAND-CHECK**

> T1: I'm 19 and coming back from 10 days in Italy, first trip this year. I bought one 750 ml bottle of Chianti (13%) for $20. Do I owe anything?

**Turn 1: answered** (owe, owe $0.81). You'll owe about $0.81.

- Age 19 < 21: no alcohol and no tobacco allowance (R3, Decision B).
- Exemption $800 (R9): trip 240 h >= 48 h; not used in the last 30 days.
- Line 1 wine 750 ml @ 13%: exempt 0 ml, dutiable 750 ml.
- Line 1 duty: value $20 x 750/750 = $20.0000; 3% flat rate -> $0.60. Excise (still_wine_le_16, $1.07/wine_gallon): 0.198129 wine gal -> $0.211998 -> $0.21.
- Totals: duty $0.60 + excise $0.21 = $0.81.
- Figures: `exemption_usd`=800, `alcohol_allowance_ml`=0, `exempt_ml_1`=0, `dutiable_ml_1`=750, `dutiable_value_usd_1`=20.00, `duty_rate_1`=0.03, `duty_usd_1`=0.60, `excise_usd_1`=0.21, `duty_total_usd`=0.60, `excise_total_usd`=0.21, `total_owed_usd`=0.81
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R3 under_21: any of `cfr19_p148:148.33(d)`, `cfr19_p148:148.34(a)`, `hts_9804_rows:9804.00.65`, `cbp_customs_duty_info:tobacco-products`
- Cite R7 flat_rate_duty: any of `hts_9816_rows:9816.00.20`, `cfr19_p148:148.101`, `cfr19_p148:148.102(a)`, `hts_general_notes:general-note-3-b`, `hts_general_notes:general-note-3-c`, `hts_general_notes:general-note-11-a`, `cbp_customs_duty_info:determining-customs-duty`
- Cite R8 excise_general_rates: any of `ttb_tax_rates:alcohol-tax-rates-for-calendar-years-2018-to-pre`, `usc26_5001:5001(a)`, `usc26_5041:5041(b)`, `usc26_5051:5051(a)`, `cfr27_p27:27.45`
- Notes required: disclaimer, generic_state_note

### G02 (mixed_basket)

**HAND-CHECK**

> T1: Back from two weeks in Tuscany. I'm 50 and haven't used my exemption this month. I have three 750 ml bottles of Chianti ($25 each), one 700 ml bottle of grappa (40%, $35), one carton of cigarettes and 10 Italian cigars. What do I owe?

**Turn 1: answered** (owe, owe $2.50). You'll owe about $2.50.

- Line 1: ABV not stated: 12.5% default for wine (units.yaml).
- Exemption $800 (R9): trip >=48 h; not used in the last 30 days.
- Alcohol allowance 1000 ml.
- R11 ranking (3% of value per litre + excise per litre): line 2 spirits $4.3531/L; line 1 wine $1.2827/L
- Line 1 wine 2250 ml @ 12.5%: exempt 300 ml, dutiable 1950 ml.
- Line 2 spirits 700 ml @ 40%: exempt 700 ml, dutiable 0 ml.
- Line 3 cigarettes 200: exempt 200, over the allowance 0.
- Line 4 cigars 10: exempt 10, over the allowance 0.
- Line 1 duty: value $75 x 1950/2250 = $65.0000; 3% flat rate -> $1.95. Excise (still_wine_le_16, $1.07/wine_gallon): 0.515136 wine gal -> $0.551195 -> $0.55.
- Totals: duty $1.95 + excise $0.55 = $2.50.
- Figures: `exemption_usd`=800, `alcohol_allowance_ml`=1000, `exempt_ml_1`=300, `dutiable_ml_1`=1950, `dutiable_value_usd_1`=65.00, `duty_rate_1`=0.03, `duty_usd_1`=1.95, `excise_usd_1`=0.55, `exempt_ml_2`=700, `dutiable_ml_2`=0, `exempt_sticks_3`=200, `excess_sticks_3`=0, `exempt_sticks_4`=10, `excess_sticks_4`=0, `duty_total_usd`=1.95, `excise_total_usd`=0.55, `total_owed_usd`=2.50
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R11 allocate_exemption_to_highest_cost: any of `cfr19_p148:148.33(b)`
- Cite R7 flat_rate_duty: any of `hts_9816_rows:9816.00.20`, `cfr19_p148:148.101`, `cfr19_p148:148.102(a)`, `hts_general_notes:general-note-3-b`, `hts_general_notes:general-note-3-c`, `hts_general_notes:general-note-11-a`, `cbp_customs_duty_info:determining-customs-duty`
- Cite R8 excise_general_rates: any of `ttb_tax_rates:alcohol-tax-rates-for-calendar-years-2018-to-pre`, `usc26_5001:5001(a)`, `usc26_5041:5041(b)`, `usc26_5051:5051(a)`, `cfr27_p27:27.45`
- Cite R5 tobacco_over_allowance: any of `cbp_customs_duty_info:tobacco-products`, `cfr19_p148:148.33(d)`, `cfr27_p41:41.190`
- Notes required: disclaimer, generic_state_note

### G04 (mixed_basket)

**HAND-CHECK**

> T1: Flying Dublin to Chicago O'Hare after 8 days. I'm 42, no exemption used this month. I have two 1 liter bottles of Irish whiskey (40%, $40 each) and 24 cans of stout, 330 ml each (4.2%, $2 each). What do I owe?

**Turn 1: answered** (owe, owe $6.70). You'll owe about $6.70.

- Exemption $800 (R9): trip 192 h >= 48 h; not used in the last 30 days.
- Alcohol allowance 1000 ml.
- R11 ranking (3% of value per litre + excise per litre): line 1 spirits $4.0531/L; line 2 beer $0.3352/L
- Line 1 spirits 2000 ml @ 40%: exempt 1000 ml, dutiable 1000 ml.
- Line 2 beer 7920 ml @ 4.2%: exempt 0 ml, dutiable 7920 ml.
- Line 1 duty: value $80 x 1000/2000 = $40.0000; 3% flat rate -> $1.20. Excise (distilled_spirits, $13.5/proof_gallon): 0.264172 gal x proof 80/100 = 0.211338 pg -> $2.853058 -> $2.85.
- Line 2 duty: value $48 x 7920/7920 = $48.0000; 3% flat rate -> $1.44. Excise (beer, $18/barrel): 2.092243 gal / 31 = 0.067492 bbl -> $1.214851 -> $1.21.
- Totals: duty $2.64 + excise $4.06 = $6.70.
- Figures: `exemption_usd`=800, `alcohol_allowance_ml`=1000, `exempt_ml_1`=1000, `dutiable_ml_1`=1000, `dutiable_value_usd_1`=40.00, `duty_rate_1`=0.03, `duty_usd_1`=1.20, `excise_usd_1`=2.85, `exempt_ml_2`=0, `dutiable_ml_2`=7920, `dutiable_value_usd_2`=48.00, `duty_rate_2`=0.03, `duty_usd_2`=1.44, `excise_usd_2`=1.21, `duty_total_usd`=2.64, `excise_total_usd`=4.06, `total_owed_usd`=6.70
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R11 allocate_exemption_to_highest_cost: any of `cfr19_p148:148.33(b)`
- Cite R7 flat_rate_duty: any of `hts_9816_rows:9816.00.20`, `cfr19_p148:148.101`, `cfr19_p148:148.102(a)`, `hts_general_notes:general-note-3-b`, `hts_general_notes:general-note-3-c`, `hts_general_notes:general-note-11-a`, `cbp_customs_duty_info:determining-customs-duty`
- Cite R8 excise_general_rates: any of `ttb_tax_rates:alcohol-tax-rates-for-calendar-years-2018-to-pre`, `usc26_5001:5001(a)`, `usc26_5041:5041(b)`, `usc26_5051:5051(a)`, `cfr27_p27:27.45`
- Cite IL arrival-state flag: any of `state_il:general-information`
- Notes required: disclaimer, state_flag:IL

### G07 (mixed_basket)

**HAND-CHECK**

> T1: Coming back from two weeks in Spain. I'm 44, first trip this year. I bought sixteen 750 ml bottles of wine at $12 each and one 1 liter bottle of gin ($30, 40%). How much will I pay?

*Judgement:* 16 x 750 ml + 1 L = 13 L > 12 L flag (Decision D): large-quantity note and escalate.

**Turn 1: escalated** (escalated). That is a large quantity (13 L): CBP may treat it as commercial. Contact your port of entry before travelling; this needs a CBP officer.

- Line 1: ABV not stated: 12.5% default for wine (units.yaml).
- Exemption $800 (R9): trip >=48 h; not used in the last 30 days.
- Alcohol allowance 1000 ml.
- R11 ranking (3% of value per litre + excise per litre): line 2 spirits $3.7531/L; line 1 wine $0.7627/L
- Line 1 wine 12000 ml @ 12.5%: exempt 0 ml, dutiable 12000 ml.
- Line 2 spirits 1000 ml @ 40%: exempt 1000 ml, dutiable 0 ml.
- Line 1 duty: value $192 x 12000/12000 = $192.0000; 3% flat rate -> $5.76. Excise (still_wine_le_16, $1.07/wine_gallon): 3.170065 wine gal -> $3.391969 -> $3.39.
- Totals: duty $5.76 + excise $3.39 = $9.15.
- ESCALATE: total alcohol 13000 ml > 12000 ml (R10, Decision D).
- Figures: `exemption_usd`=800, `alcohol_allowance_ml`=1000
- Cite R10 large_quantity_flag: any of `cbp_customs_duty_info:alcoholic-beverages`, `cfr19_p148:148.33(e)`
- Notes required: disclaimer, large_quantity

### G08 (mixed_basket)

**HAND-CHECK**

> T1: Flying home from Amsterdam after 6 days. I'm 32 and haven't used an exemption this month. I have two 1 liter bottles of Dutch gin (35%, $28 each), two 750 ml bottles of French wine (12%, $16 each) and 50 Dutch cigars. What's owed?

**Turn 1: answered** (owe, owe $4.72). You'll owe about $4.72.

- Exemption $800 (R9): trip 144 h >= 48 h; not used in the last 30 days.
- Alcohol allowance 1000 ml.
- R11 ranking (3% of value per litre + excise per litre): line 1 spirits $3.3364/L; line 2 wine $0.9227/L
- Line 1 spirits 2000 ml @ 35%: exempt 1000 ml, dutiable 1000 ml.
- Line 2 wine 1500 ml @ 12%: exempt 0 ml, dutiable 1500 ml.
- Line 3 cigars 50: exempt 50, over the allowance 0.
- Line 1 duty: value $56 x 1000/2000 = $28.0000; 3% flat rate -> $0.84. Excise (distilled_spirits, $13.5/proof_gallon): 0.264172 gal x proof 70/100 = 0.184920 pg -> $2.496426 -> $2.50.
- Line 2 duty: value $32 x 1500/1500 = $32.0000; 3% flat rate -> $0.96. Excise (still_wine_le_16, $1.07/wine_gallon): 0.396258 wine gal -> $0.423996 -> $0.42.
- Totals: duty $1.80 + excise $2.92 = $4.72.
- Figures: `exemption_usd`=800, `alcohol_allowance_ml`=1000, `exempt_ml_1`=1000, `dutiable_ml_1`=1000, `dutiable_value_usd_1`=28.00, `duty_rate_1`=0.03, `duty_usd_1`=0.84, `excise_usd_1`=2.50, `exempt_ml_2`=0, `dutiable_ml_2`=1500, `dutiable_value_usd_2`=32.00, `duty_rate_2`=0.03, `duty_usd_2`=0.96, `excise_usd_2`=0.42, `exempt_sticks_3`=50, `excess_sticks_3`=0, `duty_total_usd`=1.80, `excise_total_usd`=2.92, `total_owed_usd`=4.72
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R11 allocate_exemption_to_highest_cost: any of `cfr19_p148:148.33(b)`
- Cite R7 flat_rate_duty: any of `hts_9816_rows:9816.00.20`, `cfr19_p148:148.101`, `cfr19_p148:148.102(a)`, `hts_general_notes:general-note-3-b`, `hts_general_notes:general-note-3-c`, `hts_general_notes:general-note-11-a`, `cbp_customs_duty_info:determining-customs-duty`
- Cite R8 excise_general_rates: any of `ttb_tax_rates:alcohol-tax-rates-for-calendar-years-2018-to-pre`, `usc26_5001:5001(a)`, `usc26_5041:5041(b)`, `usc26_5051:5051(a)`, `cfr27_p27:27.45`
- Cite R5 tobacco_over_allowance: any of `cbp_customs_duty_info:tobacco-products`, `cfr19_p148:148.33(d)`, `cfr27_p41:41.190`
- Notes required: disclaimer, generic_state_note

### G10 (mixed_basket)

**HAND-CHECK**

> T1: Returning from 12 days in Germany. I'm 64, first trip this year. I have one 750 ml bottle of German riesling (11%, $20), one 700 ml bottle of German schnapps (38%, $25) and six 500 ml bottles of German beer (5%, $3 each). What do I owe?

**Turn 1: answered** (owe, owe $1.49). You'll owe about $1.49.

- Exemption $800 (R9): trip 288 h >= 48 h; not used in the last 30 days.
- Alcohol allowance 1000 ml.
- R11 ranking (3% of value per litre + excise per litre): line 2 spirits $3.7818/L; line 1 wine $1.0827/L; line 3 beer $0.3334/L
- Line 1 wine 750 ml @ 11%: exempt 300 ml, dutiable 450 ml.
- Line 2 spirits 700 ml @ 38%: exempt 700 ml, dutiable 0 ml.
- Line 3 beer 3000 ml @ 5%: exempt 0 ml, dutiable 3000 ml.
- Line 1 duty: value $20 x 450/750 = $12.0000; 3% flat rate -> $0.36. Excise (still_wine_le_16, $1.07/wine_gallon): 0.118877 wine gal -> $0.127199 -> $0.13.
- Line 3 duty: value $18 x 3000/3000 = $18.0000; 3% flat rate -> $0.54. Excise (beer, $18/barrel): 0.792516 gal / 31 = 0.025565 bbl -> $0.460171 -> $0.46.
- Totals: duty $0.90 + excise $0.59 = $1.49.
- Figures: `exemption_usd`=800, `alcohol_allowance_ml`=1000, `exempt_ml_1`=300, `dutiable_ml_1`=450, `dutiable_value_usd_1`=12.00, `duty_rate_1`=0.03, `duty_usd_1`=0.36, `excise_usd_1`=0.13, `exempt_ml_2`=700, `dutiable_ml_2`=0, `exempt_ml_3`=0, `dutiable_ml_3`=3000, `dutiable_value_usd_3`=18.00, `duty_rate_3`=0.03, `duty_usd_3`=0.54, `excise_usd_3`=0.46, `duty_total_usd`=0.90, `excise_total_usd`=0.59, `total_owed_usd`=1.49
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R11 allocate_exemption_to_highest_cost: any of `cfr19_p148:148.33(b)`
- Cite R7 flat_rate_duty: any of `hts_9816_rows:9816.00.20`, `cfr19_p148:148.101`, `cfr19_p148:148.102(a)`, `hts_general_notes:general-note-3-b`, `hts_general_notes:general-note-3-c`, `hts_general_notes:general-note-11-a`, `cbp_customs_duty_info:determining-customs-duty`
- Cite R8 excise_general_rates: any of `ttb_tax_rates:alcohol-tax-rates-for-calendar-years-2018-to-pre`, `usc26_5001:5001(a)`, `usc26_5041:5041(b)`, `usc26_5051:5051(a)`, `cfr27_p27:27.45`
- Notes required: disclaimer, generic_state_note

### I02 (clarify)

**HAND-CHECK**

> T1: Day trip to Tijuana. I bought one 750 ml bottle of tequila.
> T2: I'm 29, I haven't used it this month, and I'm walking back to San Diego. I live in San Diego.

**Turn 1: clarify** (clarify). Are you 21 or older, have you used your duty-free exemption in the last 30 days, and which US state do you cross into?

- Clarify fields: age_21_plus, exemption_used_last_30_days, arrival_state
- Clarify: missing answer-changing facts -> age_21_plus, exemption_used_last_30_days, arrival_state.

**Turn 2: answered** (nothing_owed, owe $0.00). You owe nothing: it is all within your exemption.

- Line 1: ABV not stated: 40% default for spirits (units.yaml).
- Exemption $800 (R9): arrived directly from Mexico (no 48-hour minimum); not used in the last 30 days.
- Alcohol allowance 1000 ml.
- Line 1 spirits 750 ml @ 40%: exempt 750 ml, dutiable 0 ml.
- Figures: `exemption_usd`=800, `alcohol_allowance_ml`=1000, `exempt_ml_1`=750, `dutiable_ml_1`=0
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite CA arrival-state flag: any of `state_ca:travel-by-steamship-or-airplane`, `state_ca:returning-from-mexico`
- Notes required: disclaimer, state_flag:CA

### I06 (clarify)

**HAND-CHECK**

> T1: Back from 3 days in Quebec City. I'm 35. I bought two 750 ml bottles of Canadian wine (12%) at $20 each. What do I owe?
> T2: Yes, I used it two weeks ago on a trip to London.

**Turn 1: clarify** (clarify). Have you used your duty-free exemption in the last 30 days, and which US state do you arrive in?

- Clarify fields: exemption_used_last_30_days, arrival_state
- Clarify: missing answer-changing facts -> exemption_used_last_30_days, arrival_state.

**Turn 2: answered** (owe, owe $0.42). You'll owe about $0.42.

- Exemption $200 (R9 -> R1): the $800 exemption was used in the last 30 days.
- R1 all-or-nothing triggered (1500 ml alcohol > 150 ml): NOTHING is exempt.
- Line 1 wine 1500 ml @ 12%: exempt 0 ml, dutiable 1500 ml.
- Line 1 duty: value $40 x 1500/1500 = $40.0000; free: product of USMCA (S) partner, if it qualifies as originating -> $0.00. Excise (still_wine_le_16, $1.07/wine_gallon): 0.396258 wine gal -> $0.423996 -> $0.42.
- Totals: duty $0.00 + excise $0.42 = $0.42.
- Figures: `exemption_usd`=200, `alcohol_allowance_ml`=150, `exempt_ml_1`=0, `dutiable_ml_1`=1500, `dutiable_value_usd_1`=40.00, `duty_rate_1`=0, `duty_usd_1`=0.00, `excise_usd_1`=0.42, `duty_total_usd`=0.00, `excise_total_usd`=0.42, `total_owed_usd`=0.42
- Cite R9 which_exemption: any of `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`
- Cite R1 exemption_200_all_or_nothing: any of `cfr19_p148:148.51(a)`, `cfr19_p148:148.51(b)`, `cfr19_p148:148.51(c)`, `cbp_types_exemptions:overview`
- Cite R7 flat_rate_duty: any of `hts_9816_rows:9816.00.20`, `cfr19_p148:148.101`, `cfr19_p148:148.102(a)`, `hts_general_notes:general-note-3-b`, `hts_general_notes:general-note-3-c`, `hts_general_notes:general-note-11-a`, `cbp_customs_duty_info:determining-customs-duty`
- Cite R8 excise_general_rates: any of `ttb_tax_rates:alcohol-tax-rates-for-calendar-years-2018-to-pre`, `usc26_5001:5001(a)`, `usc26_5041:5041(b)`, `usc26_5051:5051(a)`, `cfr27_p27:27.45`
- Notes required: disclaimer, generic_state_note, fta_caveat
