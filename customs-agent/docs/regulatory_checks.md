# Regulatory checks (Day 1)

Resolves the VERIFY rows in `CLAUDE.md` ("Regulatory facts: status") before rules are written to `data/rules.yaml` / `data/rates.yaml` and before gold answers are frozen in `eval-v1`.

Each check gives: the question, the governing text (short quote + link; full text in the local corpus where available), the conclusion the system will use, a confidence level, and what it changes. Checked 2026-11-21. **Every conclusion still needs a human read of the cited text before `eval-v1` is tagged.**

## Summary

| # | Question | Conclusion for v1 | Confidence |
| --- | --- | --- | --- |
| 1 | Tobacco over the allowance: pay duty, or seized? | **Not a duty calculation.** Declare it; excess is subject to detention, seizure or abandonment. The agent gives no dollar figure. | High (CBP guidance + statute for cigarettes) |
| 2 | US-made export-labelled cigarettes coming back | Allowed **only up to the personal exemption** (e.g. 200). Excess can be voluntarily relinquished at entry without penalty; otherwise forfeited with a penalty. Do **not** offer the "American goods returned" route for excess. | High on the statute; medium on CBP practice |
| 3 | Cuban alcohol/tobacco bought in a third country (e.g. Cancún) | **Prohibited** as baggage, wherever bought. Cite 31 CFR 515.204 and 515.585(d). | High |
| 4 | Flat rate: exceptions to 3% | **Free** for goods originating in a listed trade-agreement partner, incl. Mexico and Canada (USMCA, code `S`); **4%** for Column 2 countries (Belarus, Cuba, North Korea, Russia). Excise still applies. 2026 Section 122 surcharge does not apply to Chapter 98 entries. | High for the rate column; medium for origin rules |
| 5 | Russian-origin alcohol in personal baggage | **Unresolved.** E.O. 14068 bans import; an IEEPA travel exemption may cover personal baggage. v1 **escalates** instead of answering. | Low |
| 6 | Day trips to Mexico | **$800 exemption applies** to a direct arrival from Mexico regardless of trip length; the 48-hour rule still applies to Canada and everywhere else. | High (regulation text) |

New findings (not VERIFY rows): **the flat rate has its own 30-day rule** (check 4), and **a direct arrival from Mexico gets the $800 exemption whatever the trip length** (check 6).

---

## 1. Tobacco over the allowance

**Question.** A traveller has more cigarettes or cigars than the exemption allows (e.g. 400 cigarettes with a 200 limit). Can they pay duty and tax on the excess, or is it seized?

**Governing text.**

- CBP, "Customs duty information", section *Tobacco Products*: quantities not permitted by a personal exemption are *"subject to detention, seizure, penalties, abandonment, and destruction."* Also: returning residents *"may import tobacco products only in quantities not exceeding"* the exemption amounts. [CBP](https://cbp.gov/travel/international-visitors/know-before-you-visit/customs-duty-information) · local: `data/rag-corpus/corpus/docs/cbp-duty-info--tobacco-products.md`
- 19 U.S.C. 1681a: imported cigarettes must meet labelling and certification requirements; the exemption covers only personal-use quantities allowed free under HTSUS chapter 98 subchapter IV. [uscode.house.gov](https://uscode.house.gov/us/usc/119-120/t19/s1681a/)

**Conclusion.** Treat tobacco over the allowance as **not dutiable by the traveller**: the answer is "declare all of it; the excess may be detained, seized or abandoned, and penalties are possible." No duty or excise figure is computed for the excess. For cigarettes the statute supports this (foreign cigarettes over the personal-use quantity fail the 1681a entry requirements). For cigars the basis is the CBP guidance, which covers all tobacco products.

**Changes.**
- `rules.yaml`: `tobacco_over_limit → outcome: declare_detention_risk` (no calculation).
- `compute_duty_excise` never receives excess tobacco.
- Eval type `tobacco_over_limit` (7): gold bottom line = "declare; excess subject to detention/seizure/abandonment", no dollar amount.
- `CLAUDE.md`: row "Excess tobacco" → Confirmed.

## 2. US-made export-labelled cigarettes coming back

**Question.** Cigarettes made in the US and sold for export, typically bought at a duty-free shop and marked "Tax Exempt. For Use Outside the United States". The business case said these can return as "American goods returned" (AGR) above the limit.

**Governing text.**

- 26 U.S.C. 5754(a)(1): export-labelled tobacco products may come back into the US only through narrow routes (release under 5704(d), or return to the original manufacturer). Cross-reference: *"For exception to this section for personal use, see section 5761(d)."* [Cornell LII](https://www.law.cornell.edu/uscode/text/26/5754)
- 26 U.S.C. 5761(d): no quantity beyond the personal-use quantity may be relanded as personal use; 5754 and 5761(c) do not apply to the quantity *"allowed entry free of tax and duty under chapter 98"*, and the person may *"voluntarily relinquish"* any excess at entry without the 5761(c) penalty. [Justia](https://law.justia.com/codes/us/2019/title-26/subtitle-e/chapter-52/subchapter-g/sec-5761/)
- 26 U.S.C. 5761(c): relanded export-labelled products are forfeited and destroyed; penalty is the greater of $1,000 or 5 times the tax. (Same source.)
- CBP guidance gives AGR examples (400 previously exported cigarettes admitted on proof of AGR). That guidance does not mention the export-label restriction. local: `cbp_customs_duty_information.md`

**Conclusion.** For export-labelled US cigarettes, the statute limits personal entry to the exemption quantity. **Within the allowance:** fine. **Over it:** tell the traveller to declare and voluntarily relinquish the excess at entry (no penalty); otherwise the excess is forfeited and a penalty can apply. The AGR route in CBP's guidance is not offered for excess quantities; where a traveller claims AGR proof, the agent escalates.

**Changes.**
- `check_restrictions`: flag `export_labelled_us_cigarettes`; over the allowance → `outcome: relinquish_excess`, cite 26 USC 5761(d).
- Eval: add 1–2 `tobacco_over_limit` scenarios with duty-free US cigarettes; gold = "declare; relinquish the excess".
- `CLAUDE.md`: row "US-made export-labelled cigarettes" → Confirmed (restrictive reading).

## 3. Cuban alcohol or tobacco bought in a third country

**Question.** Cuban cigars or rum bought in Mexico or Europe, not in Cuba.

**Governing text.** (Full text in `data/rag-corpus/corpus/docs/31cfr515.204.md` and `31cfr515.585.md`.)

- 31 CFR 515.204(a): persons subject to US jurisdiction may not *"purchase, transport, import, or otherwise deal in"* merchandise of Cuban origin, unless authorised.
- 31 CFR 515.585(c): US persons in a third country may buy Cuban-origin goods there.
- 31 CFR 515.585(d): they may bring third-country purchases of Cuban-origin goods home as accompanied baggage for personal use, but *"This paragraph does not apply to"* Cuban-origin alcohol or tobacco.
- CBP Info Center article 1389 (published 2026-02-27): Cuban alcohol and tobacco bought in a third country are for consumption **outside** the US. [CBP](https://www.help.cbp.gov/s/article/Article-1389?language=en_US) · local: `cbp_info_cuban_cigars.md`
- OFAC FAQ 719: products acquired in Cuba may no longer be brought back as accompanied baggage (since 2020-09-24). local: `ofac_faq_719.md`

**Conclusion.** Cuban-origin alcohol and tobacco cannot be brought in as personal baggage, **wherever bought**. The personal-exemption allowances do not apply. Cite **31 CFR 515.204(a)** for the prohibition and **515.585(d)** for why the third-country authorisation does not help; cite FAQ 719 only when bought in Cuba.

**Changes.**
- `rules.yaml`: `cuban_origin` → prohibited, citations `31cfr515.204`, `31cfr515.585(d)`.
- Eval type `cuban_origin` (7): gold citations as above.
- `CLAUDE.md`: row "Cuban goods bought in a third country" → Confirmed.

## 4. Flat-rate exceptions

**Question.** The flat rate on the next $1,000 over the exemption is 3%. Is it different for Mexican tequila, Canadian whisky, or Russian vodka?

**Governing text.**

- HTSUS 9816.00.20 (fetched from the USITC API; local `corpus/docs/htsus9816.00.20.md`):
  - General: 3 percent of fair retail value
  - Special: **Free (BH, CL, CO, IL, JO, KR, MA, OM, P, PA, PE, S, SG)**
  - Column 2: **4 percent**
- USITC Pub. 5060 (2020): special programme indicator for USMCA is *"S or S+"*. [USITC](https://usitc.gov/publications/tariff_affairs/pub5060.pdf)
- Column 2 (no normal trade relations): Belarus, Cuba, North Korea, Russia. CBP's duty page also states 4% for Column 2 goods.
- Heading 9816 conditions (same file): articles for personal use or gifts, aggregate fair retail value not over $1,000, and the person *"has not received the benefits thereof within the 30 days immediately preceding his arrival"*.
- 2026 Section 122 surcharge (heading 9903.03.01, 24 Feb – 24 Jul 2026): CBP states it does not apply to goods properly entered under a Chapter 98 provision. [CBP CSMS](https://content.govdelivery.com/accounts/usdhscbp/bulletins/40b3b7b)

**Conclusion.**
- Flat-rate duty on alcohol over the allowance is **0%** when the goods originate in a listed partner country (code `S` = USMCA: Mexico, Canada; others: Bahrain, Chile, Colombia, Israel, Jordan, Korea, Morocco, Oman, CAFTA-DR (`P`), Panama, Peru, Singapore), **4%** for Column 2 origins, **3%** otherwise. Origin = where made, not where bought (Scotch bought in Mexico is 3%).
- **Excise is still due** whatever the duty rate.
- The flat rate has its **own 30-day rule**: if the traveller used it in the last 30 days, normal HTSUS rates apply instead. v1: ask only if the traveller says they travelled recently; otherwise state the assumption.
- No 2026 surcharge on top of the flat rate.

**Changes.**
- `rates.yaml`: `flat_rate: {general: 0.03, column2: 0.04, free_programs: [BH, CL, CO, IL, JO, KR, MA, OM, P, PA, PE, S, SG]}` + country → programme map.
- `compute_duty_excise`: rate by **origin**; intake must capture origin separately from where bought.
- Worked example (Canadian whisky, day trip to Canada): $200 exemption does not apply (all-or-nothing), so the whole bottle goes to the flat rate. Canadian origin (USMCA) → **duty $0**; excise ≈ **$2.14**; total ≈ **$2.14** + state tax. (A day trip to Mexico is different: see check 6.)
- Eval: `alcohol_excess_800` should include at least one USMCA-origin and one ordinary-origin case.
- `CLAUDE.md`: row "Flat-rate exceptions" → Confirmed.

**Still to confirm by reading General Note 3(c)(i):** that `P` is CAFTA-DR and the full country list for each code.

## 5. Russian-origin alcohol in personal baggage

**Question.** Does the Russian import ban stop a traveller bringing back a bottle of Russian vodka?

**Governing text.**

- E.O. 14068 (2022-03-11) prohibits importing Russian-origin alcoholic beverages. OFAC FAQ 1024 summarises the ban. [OFAC](https://ofac.treasury.gov/faqs/search/1024+1027)
- OFAC FAQ 1182 notes that, in the Russia programme, transactions *"ordinarily incident to travel"* are exempt under IEEPA. [OFAC](https://ofac.treasury.gov/faqs/1182) The IEEPA travel exemption (50 U.S.C. 1702(b)(4)) covers importing accompanied baggage for personal use.
- No source found that applies the travel exemption to the alcohol import ban specifically.

**Conclusion.** Unresolved. Even if allowed, Russian goods are Column 2 (4% flat rate). **v1 does not answer this case:** `check_restrictions` flags Russian-origin alcohol and the agent escalates ("declare it; an officer decides; we can't confirm it is admissible").

**Changes.**
- `rules.yaml`: `russian_origin_alcohol → outcome: escalate`.
- Eval: 1 scenario, gold = escalate.
- `CLAUDE.md`: row stays Open, with the v1 decision.

## 6. Day trips to Mexico (found while writing `data/rules.yaml`)

**Question.** The earlier worked example sent a same-day Tijuana trip to the $200 exemption because the trip was under 48 hours. Is that right?

**Governing text.** 19 CFR 148.35(a): the $800 exemption needs 48 hours abroad, but it *"may be allowed"* on a direct arrival from Mexico without regard to the time spent outside the US. local: `data/rag-corpus/corpus/docs/19cfr148.35.md`

**Conclusion.** A returning resident arriving **directly from Mexico** gets the $800 exemption (and its 1 L alcohol allowance) whatever the trip length, subject to the 30-day rule. The 48-hour rule still applies to Canada and all other countries. The earlier Tijuana example was wrong: one 750 ml bottle of tequila after a day trip to Mexico owes **$0**. The all-or-nothing $200 example now uses a day trip to Canada.

**Changes.**
- `rules.yaml`: `standard_800.applies_when.min_hours_waived_for_direct_arrival_from: [MX]`.
- Intake must capture whether the traveller arrived directly from Mexico.
- Eval type `exemption_200_all_or_nothing` (8): use short trips to Canada or other countries, never direct arrivals from Mexico; add a Mexico day-trip scenario whose gold answer uses the $800 exemption.
- `CLAUDE.md`: worked examples corrected.

---

## What to do next

1. Read the cited text for checks 1–4 and mark each conclusion agreed (or correct it here).
2. Update `CLAUDE.md` statuses and worked examples (done alongside this file; revert if you disagree).
3. Write `data/rules.yaml` and `data/rates.yaml` from the "Changes" lines.
4. Add to the corpus: 19 USC 1681a, 26 USC 5754 and 5761, HTSUS General Note 3, OFAC FAQs 1022/1024/1182 (Russia), so every citation above is retrievable.

---

## Glossary

**Government bodies**

| Abbreviation | Stands for | Role in this project |
| --- | --- | --- |
| CBP | U.S. Customs and Border Protection | Border agency; assesses what travellers owe and enforces the rules. Traveller pages and Info Center articles are in the corpus. |
| OFAC | Office of Foreign Assets Control (U.S. Treasury) | Runs sanctions programmes (Cuba, Russia). Source of FAQs 719, 769, 1024, 1182. |
| TTB | Alcohol and Tobacco Tax and Trade Bureau (U.S. Treasury) | Sets and publishes federal excise tax rates on alcohol and tobacco. |
| USITC | U.S. International Trade Commission | Maintains and publishes the HTSUS; its API is used by `fetch_corpus.py`. |

**Legal documents**

| Abbreviation | Stands for | What it is |
| --- | --- | --- |
| CFR | Code of Federal Regulations | Agency rules. "19 CFR 148.51" = Title 19 (customs), Part 148, section 51. 31 CFR = Treasury / sanctions (Cuba: Part 515). 27 CFR = alcohol and tobacco tax. |
| eCFR | Electronic Code of Federal Regulations | Official, continuously updated online CFR; source for the corpus. |
| USC | United States Code | Laws passed by Congress. 19 USC = customs law (1681a: cigarette import requirements). 26 USC = tax law (5754, 5761: export-labelled tobacco). |
| HTSUS (HTS) | Harmonized Tariff Schedule of the United States | Official list of duty rates for every product. Chapter 98 holds the traveller provisions: 9804.00.65 ($800 exemption), 9816.00.20 (3% flat rate). |
| GN | General Note (of the HTSUS) | Notes at the front of the tariff schedule. GN 3(c)(i) lists the special trade-programme codes. |
| E.O. | Executive Order | Presidential order. E.O. 14068 (2022) bans imports of Russian alcohol, seafood and non-industrial diamonds. |
| IEEPA | International Emergency Economic Powers Act | Law most sanctions are issued under; exempts transactions "ordinarily incident to travel", which leaves Russian alcohol in baggage unresolved. |
| Section 122 | Section 122 of the Trade Act of 1974 | Basis of the temporary 10% import surcharge (24 Feb – 24 Jul 2026); not applied to Chapter 98 (traveller) entries. |
| CSMS | Cargo Systems Messaging Service | CBP's official bulletins to importers and brokers. |

**Trade terms**

| Abbreviation | Stands for | Meaning |
| --- | --- | --- |
| AGR | American Goods Returned | US-made goods coming back after export, normally duty-free. Limited for export-labelled cigarettes (check 2). |
| FTA | Free Trade Agreement | Agreements under which the flat rate is Free for goods made in partner countries. |
| USMCA | United States–Mexico–Canada Agreement | Replaced NAFTA in 2020. HTSUS code `S` / `S+`. |
| NAFTA | North American Free Trade Agreement | 1994–2020 predecessor of USMCA. |
| CAFTA-DR | Dominican Republic–Central America FTA | Costa Rica, Dominican Republic, El Salvador, Guatemala, Honduras, Nicaragua. Probably code `P` (to confirm). |
| CBI | Caribbean Basin Initiative | US trade programme for Caribbean countries; basis of the 2-liter alcohol allowance when arriving from them. |
| NTR / Column 2 | Normal Trade Relations | Countries with NTR pay "general" (Column 1) rates. Countries without it pay Column 2 rates: Belarus, Cuba, North Korea, Russia (4% flat rate). |
| IRT | Internal Revenue Tax | CBP's term for the federal excise tax it collects for TTB on alcohol and tobacco. |

**Units and tax terms**

| Term | Meaning |
| --- | --- |
| ABV | Alcohol by volume (e.g. 13% wine, 40% spirits). |
| Proof | Twice the ABV: 40% ABV = 80 proof. |
| Proof gallon | One US gallon at 100 proof (50% ABV). Spirits excise: $13.50 per proof gallon. |
| Wine gallon | One US gallon (3.785 L) of wine regardless of strength. Still wine ≤ 16% ABV: $1.07 per gallon. |

**Trade-programme codes in the HTSUS 9816.00.20 "Free" list** (only `S` confirmed; the rest to check against GN 3(c)(i))

| Code | Country / agreement | | Code | Country / agreement |
| --- | --- | --- | --- | --- |
| BH | Bahrain | | MA | Morocco |
| CL | Chile | | OM | Oman |
| CO | Colombia | | P | CAFTA-DR (to confirm) |
| IL | Israel | | PA | Panama |
| JO | Jordan | | PE | Peru |
| KR | Korea | | S | USMCA (Mexico, Canada): confirmed |
| | | | SG | Singapore |
