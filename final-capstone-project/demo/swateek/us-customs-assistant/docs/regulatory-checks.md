# Regulatory checks (plan §3, step 3)

Each check below was researched in the frozen corpus (eCFR 2026-11-13, HTS 2026 Revision 23, US Code 2024 edition, live pages retrieved 2026-11-17). For each one: the claim being checked, what the official text says, the clause ids it rests on (`source:unit`, as in `data/chunks/documents.jsonl`), and the rule proposed for v1. The machine-readable rules are in `pack/rules/` with `status: proposed`.

**Status: signed off by the user on 2026-11-17**, with decisions A–G as recorded at the end (§ Decisions). All rows in `pack/rules/` are `signed_off`. A change to any row needs a new sign-off and a re-check of the eval gold.

| # | Topic | Result | Changes the business case? |
|---|---|---|---|
| R1 | $200 exemption, all-or-nothing | Confirmed (19 CFR 148.51(b)) | Yes, and example 4 changes again (see R9) |
| R2 | Caribbean Basin 2 litres | Confirmed; it is 148.33(d)(3)(ii); the country list needs a decision | Yes (adds a rule) |
| R3 | Under 21 | Alcohol: confirmed. Tobacco: CBP guidance says 21+ too | Partly |
| R4 | Cuban goods bought in a third country | Prohibited: 31 CFR 515.585(d) excludes Cuban alcohol and tobacco | Citation changes |
| R5 | Extra tobacco: taxed or seized? | Seized, as the business case said (CBP guidance) | No (mentor's doubt resolved) |
| R6 | US cigarettes returning | The business case had it backwards: only the personal quantity may return | Yes |
| R7 | 3% flat rate and origin | 3% up to $1,000; trade-agreement goods can be free; Column 2 countries 4% | Yes (needs a decision) |
| R8 | Which excise rate | The general rates; reduced rates are for producers and electing importers | No |
| R9 | 48-hour and 30-day rules | **Mexico arrivals get $800 regardless of time away** | **Yes: the Tijuana example is $800, not $200** |
| R10 | Personal use vs commercial | No federal number; CBP decides on the spot | Needs a decision (flag threshold) |
| R11 | Which litre is exempt | Exemption goes to the highest combined duty + tax first | Yes (adds a rule) |
| R12 | Origin from brand names | No rule exists; brand is not origin | Needs a decision (ask vs assume) |

---

## R1. The $200 exemption is all-or-nothing

**Claim (business case, example 4):** "$200 exemption holds only 150 ml… the other 600 ml is over the allowance."

**Finding.** The $200 exemption (section 321(a)(2)(B)) applies to a returning resident who is not entitled to the $800 exemption. "No article accompanying a person … will be exempted … if any article accompanying such person is subject to duty or tax" because of the limits: total value over $200, or more than 50 cigarettes, 10 cigars, 150 ml of alcohol or 150 ml of alcoholic perfume. Family grouping is not allowed. CBP's own example: a $300 pot after 36 hours abroad is dutiable on the full $300.

**Rests on:** `cfr19_p148:148.51(a)`, `cfr19_p148:148.51(b)`, `cfr19_p148:148.51(c)`, `cbp_types_exemptions:overview`.

**v1 rule.** On the $200 exemption, if any line exceeds its limit (50 cigarettes, 10 cigars, 150 ml alcohol) or the in-scope total exceeds $200, **nothing** is exempt: every line is dutiable and taxable. No family grouping.

## R2. Two litres from Caribbean Basin beneficiary countries

**Claim:** "1 liter … from any country except a US insular possession."

**Finding.** 19 CFR 148.33(d)(3)(ii): "An individual returning directly from a beneficiary country as defined in U.S. Note 4 to Chapter 98 … may include … not more than 2 liters of alcoholic beverages if at least 1 liter is the product of one or more beneficiary countries." HTSUS 9804.00.72 says the same. U.S. Note 4 defines "beneficiary country" as "a country listed in general notes 7(a) or 11(a)". The current General Note 7(a) (Revision 23) lists: Antigua and Barbuda, Aruba, Bahamas, Barbados, Belize, Curaçao, Dominica, Grenada, Guyana, Haiti, Jamaica, Montserrat, (Netherlands Antilles, eligibility ended), St. Kitts and Nevis, Saint Lucia, Saint Vincent and the Grenadines, Trinidad and Tobago, British Virgin Islands.

Two inconsistencies:
- General Note 11 is now USMCA (it used to be the Andean programme), so Note 4's "11(a)" reference reads as stale.
- CBP's "Types of Exemptions" page lists a longer, older set (adds Bolivia, Colombia, Costa Rica, Dominican Republic, Ecuador, El Salvador, Guatemala, Honduras, Nicaragua, Panama, Peru).

→ **Decision A.**

**Rests on:** `cfr19_p148:148.33(d)`, `hts_9804_rows:9804.00.72`, `hts_ch98_pdf:subchapter-iv-u-s-note-4`, `hts_general_notes:general-note-7-a`, `cbp_types_exemptions:overview`.

**v1 rule.** Arriving directly from a beneficiary country: up to 2 L in the exemption if at least 1 L is a product of a beneficiary country; otherwise 1 L.

## R3. Under 21

**Finding.** Alcohol: "No alcoholic beverages will be included in the case of an individual who has not attained the age of 21" (148.33(d)(2); also 9804.00.65). In a family group, an under-21 member's exemption is not applied to alcohol (148.34(a)). Tobacco: the regulation and the HTS text set no age, but CBP's guidance says "The tobacco exemption is available to each adult 21 years of age or over." → **Decision B.**

**Rests on:** `cfr19_p148:148.33(d)`, `cfr19_p148:148.34(a)`, `hts_9804_rows:9804.00.65`, `cbp_customs_duty_info:tobacco-products`.

**v1 rule.** Under 21: no alcohol in the exemption, so all alcohol is dutiable and taxable. Tobacco per Decision B. Age is a clarify trigger whenever the basket has alcohol or tobacco.

## R4. Cuban-origin alcohol and tobacco bought outside Cuba

**Claim:** banned "wherever bought" (OFAC FAQ 719).

**Finding.** FAQ 719 covers goods acquired **in Cuba**: since 24 Sep 2020, travellers "may no longer return to the United States with alcohol and/or tobacco products acquired in Cuba" (also 31 CFR 515.560(c), last sentences). For a **third country** (e.g. Cancún), the right authority is:
- 31 CFR 515.204(a): no person subject to US jurisdiction may import merchandise of Cuban origin unless authorised.
- 515.585(c): buying Cuban-origin goods while in a third country is authorised.
- 515.585(d): importing such goods as accompanied baggage for personal use is authorised, but "**This paragraph does not apply to the importation into the United States of Cuban-origin alcohol or tobacco products.**"
- OFAC FAQ 720 says the same and cites 515.585(c)–(d).

**Rests on:** `cfr31_p515:515.204(a)`, `cfr31_p515:515.585(c)`, `cfr31_p515:515.585(d)`, `ofac_cuba_faqs:faq-720`, `ofac_cuba_faqs:faq-719`, `cfr31_p515:515.560(c)`, `cbp_mexico_trip:prohibited-permissible-items` ("Cuban cigars are prohibited").

**v1 rule.** Cuban-origin alcohol or tobacco is prohibited wherever it was bought. No allowance applies to it, it is not counted in any limit, and the answer says to leave it behind or declare it and expect it to be taken. Citations: third country → 515.204(a) + 515.585(d) + FAQ 720; bought in Cuba → 515.560(c) + FAQ 719.

## R5. Tobacco over the allowance: taxed or seized?

**Claim:** "not taxed: subject to detention, seizure, penalties or destruction." The mentor understood that CBP may tax it.

**Finding.** CBP's current guidance: "Returning resident travelers may import tobacco products only in quantities not exceeding the amounts specified in the personal exemptions … Any quantities of tobacco products not permitted by a personal exemption are subject to detention, seizure, penalties, abandonment, and destruction." Consistent with 27 CFR 41.190: a person importing tobacco "for personal use, in such quantities as may be allowed by [CBP] without payment of tax, is not required to have an importer's permit."

**Rests on:** `cbp_customs_duty_info:tobacco-products`, `cfr19_p148:148.33(d)`, `cfr27_p41:41.190`.

**v1 rule (data-driven, as the mentor asked).** `tobacco_excess_outcome: seizure_risk`. Tobacco over the allowance is not taxed in the answer. The answer says the excess may be detained or seized and penalised, and to declare it and let the officer decide. No duty or excise is computed for tobacco, so the planner skips `compute_duty_excise` for tobacco-only baskets. Tobacco excise rates are kept in `rates.yaml` for reference only.

## R6. US-made cigarettes coming back

**Claim (example 3):** "cigarettes made in the US and exported can come back as American goods returned, if you can prove it."

**Finding: reversed.** 26 USC 5754(a) restricts re-importing US-made, export-labelled tobacco. 5761(c) penalises relanding such products: "the greater of $1,000 or 5 times the amount of the tax", with forfeiture. But 5761(c)–(d) do not apply to "the quantity allowed entry free of tax and duty under … chapter 98", and "No quantity … other than [that] may be relanded or received as a personal use quantity". The traveller "may voluntarily relinquish … at the time of entry any excess … without incurring the penalty". CBP's page has a confusing "American Goods Returned" example, but the statute governs.

**Rests on:** `usc26_5754:5754(a)`, `usc26_5761:5761(c)`, `usc26_5761:5761(d)`, `cbp_customs_duty_info:tobacco-products`.

**v1 rule.** US-made, export-labelled cigarettes (often what duty-free shops sell: "Tax exempt, for use outside the US") count against the same allowance (200). Any excess: the traveller can give it up voluntarily at entry with no penalty; otherwise it is forfeited and a penalty of at least $1,000 can apply. No "American goods returned" exception is offered.

## R7. The flat 3% duty, its cap, and origin

**Finding.**
- HTSUS 9816.00.20 / 19 CFR 148.101–148.102: articles for personal use, accompanying the traveller, up to **$1,000** fair retail value in total, get a flat duty of **3%** of the fair retail value (once every 30 days). Family members travelling together may group the $1,000 allowance (148.103).
- Above $1,000, the excess is classified and assessed at normal tariff rates (148.101).
- 9816.00.20 Special column: **Free** for goods qualifying under BH, CL, CO, IL, JO, KR, MA, OM, P, PA, PE, **S**, SG. GN 3(c)(i) gives the symbols (e.g. S = USMCA, P = CAFTA-DR, CO = Colombia, PE = Peru, PA = Panama), and GN 11(a) confirms that USMCA-originating goods take the "S" rate.
- Column 2: **4%** for products of North Korea, Belarus, Russia and Cuba (GN 3(b); CBP's Cuba section says the same).
- Goods from US insular possessions: 1.5% (out of scope).

**Rests on:** `hts_9816_rows:9816.00.20`, `cfr19_p148:148.101`, `cfr19_p148:148.102(a)`, `cfr19_p148:148.103(a)`, `hts_ch98_pdf:subchapter-xvi-u-s-note-1`, `hts_general_notes:general-note-3-b`, `hts_general_notes:general-note-3-c`, `hts_general_notes:general-note-11-a`, `cbp_customs_duty_info:determining-customs-duty`.

**v1 rule.**
- Duty on the dutiable alcohol = 3% of the fair retail value of the excess (4% for a Column 2 origin).
- If the dutiable value exceeds $1,000, escalate (normal tariff rates are out of scope).
- Trade-agreement origin per **Decision C**.
- One traveller per answer: family grouping per **Decision F**.

## R8. Which excise rate applies to a traveller

**Finding.** TTB's rate tables: the reduced beer and spirits rates and the wine credits apply to domestic producers and to "electing U.S. importers" a foreign producer has assigned them to. "U.S. importers who are not assigned a reduced rate" pay the general rate. Statutory rates:
- spirits $13.50 per proof gallon (26 USC 5001(a)(1));
- still wine $1.07 / $1.57 / $3.15 per wine gallon for ≤16%, 16–21% and 21–24% ABV; sparkling $3.40; artificially carbonated $3.30; hard cider $0.226 (5041(b));
- beer $18 per 31-gallon barrel (5051(a); 27 CFR 27.45 for imports);
- wine over 24% is taxed as spirits (5001(a)(3)).

A traveller is not an electing importer, so **the general rates apply**.

**Rests on:** `ttb_tax_rates:alcohol-tax-rates-for-calendar-years-2018-to-pre`, `usc26_5001:5001(a)`, `usc26_5041:5041(b)`, `usc26_5051:5051(a)`, `cfr27_p27:27.45`, `ttb_tax_rates:tobacco-current-tax-rates-view-historic-tax-rate` (reference).

**v1 rule.** Rate table in `pack/rules/rates.yaml`, as of 2026-11-17. Conversions:
- 1 US gallon = 3.785411784 L;
- proof = 2 × ABV%;
- proof gallons = gallons × proof / 100;
- 1 barrel = 31 gallons.

Each tax and duty line is rounded half-up to the cent, then summed. (CBP says purchase totals for joint declarations are rounded to the dollar; the answer is labelled an estimate.)

## R9. The 48-hour and 30-day conditions (and Mexico)

**Finding.**
- The $800 exemption needs at least **48 hours** abroad (148.35(a), computed exactly, 148.35(c)), "**except** … The $800 exemption may be allowed on articles acquired abroad by a returning resident arriving directly from **Mexico** without regard to the length of time" (148.35(a)). The 9804.00.65 headnote and CBP's "What to Expect" page agree: "This time limit does not apply if you are returning from Mexico or from the U.S. Virgin Islands."
- It cannot be used if it was used in the **30 days** before arrival, counting back from the day before arrival (148.36(a)–(b)). (CBP pages say "every 31 days"; the regulation's computation gives the same result.)
- A traveller not entitled to the $800 falls to the $200 exemption (R1).

**Consequence:** a **day trip to Tijuana gets the $800 exemption** (and its 1 litre), unless it was used in the last 30 days. Both the business case ($200) and the mentor's correction ($200, all-or-nothing) are wrong for Mexico. For the $200 / all-or-nothing case, the examples should use a short trip to **Canada** or anywhere else other than Mexico, or a repeat trip within 30 days.

**Rests on:** `cfr19_p148:148.35(a)`, `cfr19_p148:148.35(c)`, `cfr19_p148:148.36(a)`, `cfr19_p148:148.36(b)`, `hts_9804_rows:9804.00.65`, `cbp_what_to_expect:paying-duties`, `cbp_types_exemptions:overview`.

**v1 rule.**
```
exemption = 800  if (trip_hours ≥ 48 or arrived_directly_from == Mexico) and not used_in_last_30_days
            200  otherwise
(insular possessions → out of scope)
```

## R10. Personal use vs commercial quantity

**Finding.** No federal number. "While federal regulations do not specify a limit on the amount of alcohol you may bring back beyond the personal exemption amount, unusual quantities may raise suspicions … CBP officers … are authorized to make on-the-spot determinations that an importation is for commercial purposes", in which case a permit and formal entry may be needed. The traveller should contact the port in advance for a substantial quantity. Articles "intended for sale" never get the exemption (148.33(e)).

**Rests on:** `cbp_customs_duty_info:alcoholic-beverages`, `cfr19_p148:148.33(e)`.

**v1 rule.** No commercial verdict. Above a flag threshold (**Decision D**), the answer adds "large quantity: CBP may treat this as commercial; contact your port of entry before travelling" and escalates. "Bought to sell" is out of scope.

## R11. Which litre is exempt in a mixed basket

**Finding.** "The $800 or $1,600 exemption will be applied to the aggregate fair retail value … of the articles … which are subject to the highest rates of duty. If an internal revenue tax is applicable, it will be combined with the duty in determining which rates are highest" (148.33(b)).

**Rests on:** `cfr19_p148:148.33(b)`.

**v1 rule.** Fill the 1 L (or 2 L) allowance with the alcohol that would cost most per litre (3% duty on its value per litre + its excise per litre), most expensive first. Fractions of a bottle are allowed, as in the business case's wine example: 2 of 3 litres dutiable, with value pro rata. If the in-scope basket's total value exceeds $800, escalate in v1, because other goods share the $800 and are not assessed.

## R12. Origin from brand names

**Finding.** No regulation maps brands to origin. What matters is whether the product is "of Cuban origin" (515.204(a)(1)). Several cigar and rum brand names are used both for Cuban products and for products made elsewhere (for example the Dominican or Honduran versions sold in the US, and a non-Cuban "Havana Club" rum). The brand alone does not settle origin. This is team knowledge, not a corpus fact: the brand table is a prompt to ask, never a legal finding.

**Rests on:** `cfr31_p515:515.204(a)`; brand list: team heuristic (`pack/rules/brands.yaml`, marked as such).

**v1 rule.** Per **Decision E**.

---

## The business-case examples, corrected

| # | Business case | Corrected (if the rows above are signed off) |
|---|---|---|
| 1 | Italy, 10 days, 4 × 750 ml wine at $30: owe about $2.97 | **Unchanged.** 3 L, 1 L exempt, 2 L dutiable; duty 3% × $80 = $2.40; excise 2 L = 0.528 gal × $1.07 = $0.57; total **$2.97**. Italy is not an FTA partner. |
| 2 | Cancún, 25 Cuban cigars + Cuban rum: banned | **Unchanged outcome, new citations:** 31 CFR 515.204(a) and 515.585(d); OFAC FAQ 720 (not only FAQ 719). |
| 3 | Dubai, 2 cartons (400): one carton over, seizure risk; "American goods returned" exception | Outcome unchanged (R5). **Exception replaced** (R6): US-made export-labelled cigarettes get no exception; the traveller can give up the excess at entry with no penalty. |
| 4 | Tijuana day trip, 750 ml tequila: $200 exemption, 600 ml over (mentor: whole bottle dutiable, ~$2.14 excise) | **Owes nothing** if 21+ and the exemption wasn't used in the last 30 days: Mexico arrivals get the $800 exemption and its 1 L regardless of time away (R9). California flag: residents crossing on foot or by private car may bring only the federal duty-free amount (1 L). If the exemption *was* used in the last 30 days: $200, all-or-nothing → the whole 750 ml is dutiable. Excise ≈ 0.198 gal × 0.80 × $13.50 = **$2.14**. Duty is 3% of its value, or **free** if the tequila qualifies as USMCA-originating (Decision C). In that case California's rule (only the federal duty-free amount, here 150 ml) is also exceeded for a resident crossing on foot or by car. |

The mentor's eval category "exemption_200_all_or_nothing" stays, built on non-Mexico day trips (e.g. Canada) and repeat trips within 30 days.

---

## States (flag + source only)

| State | What the flag says | Rests on |
|---|---|---|
| CA | By air or sea from abroad: up to 60 L for personal use. From Mexico on foot (anyone) or by private vehicle (CA residents): only the federal duty-free amount (1 L). Under 21: none. | `state_ca:travel-by-steamship-or-airplane`, `state_ca:returning-from-mexico` |
| NY | Traveller's exemption from NY alcohol tax: 1 quart (1 L if not subject to US duty) bought during the trip for personal use; the page attaches a 48-hour condition for trips abroad. Above that: Form MT-39 and NY tax; more than 90 L of liquor a year needs a temporary licence. | `state_ny:traveler-s-exemption`, `state_ny:overview` |
| FL | Florida tax doesn't apply to up to 1 gallon bought out of state and brought in by the possessor. | `state_fl:overview` (Fla. Stat. 562.16) |
| TX | Per person: 1 gal spirits, 3 gal wine, 24 × 12 oz beer, once per 30 days; Texas tax + $3 fee at the port; excess destroyed; under 21: none; no cigarettes under 21. | `state_tx:bringing-alcohol-into-texas` |
| IL | Personal imports need Illinois Liquor Control Commission authorisation and Illinois Use Tax. ilga.gov (the rule itself) was unreachable. | `state_il:general-information` |

---

## Decisions (17 Nov 2026)

| # | Question | Decided |
|---|---|---|
| A | Which countries count for the 2-litre rule (R2)? | **CBP's Types of Exemptions list** (27 countries incl. Colombia, Peru, Dominican Republic, Costa Rica…), not the shorter General Note 7(a) list. Recommendation was GN 7(a); the user chose CBP's list, which is what travellers see on cbp.gov. Known gap: for countries on CBP's list but not in GN 7(a), the legal basis is the CBP page, not the HTS. |
| B | Tobacco for under-21s (R3) | **Follow CBP**: no tobacco exemption under 21; any tobacco is at risk of seizure. |
| C | Trade-agreement origin under 9816.00.20 (R7) | **Duty free for products of listed partner countries**, with "if it qualifies as originating under the agreement; the CBP officer decides". Origin is asked for dutiable lines. |
| D | Large-quantity flag (R10) | **Over 12 litres per traveller**: note "contact your port of entry" and escalate. A UX threshold, not law. |
| E | Ambiguous brands (R12) | **Ask once** ("was it made in Cuba?"); if still unknown, treat as possibly Cuban: no allowance, declare it. |
| F | Family groups | **Per traveller**, with a scope note that family members each have their own allowance and can pool them (not calculated in v1). |
| G | Russian-origin alcohol | **Scope note only**: "Russian-origin alcohol may be prohibited; declare it and ask CBP." Not assessed. |

### Effect on the corrected examples

- Example 4 (Tijuana): with Decision C, the tequila's duty in the 30-day repeat-trip case is $0 if it qualifies as a USMCA product (tequila is made in Mexico), so the answer is the excise (≈ $2.14) plus the California flag.
- With Decision A, a traveller returning directly from e.g. the Dominican Republic or Colombia gets the 2-litre rule if at least 1 L is a product of a listed country.
