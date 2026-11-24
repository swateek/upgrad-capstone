# 1. The problem and the specification

## 1.1 Who it is for

A US resident coming home with a few bottles or a carton of cigarettes wants to know three things before the border: can I bring it, will I owe anything, and how much. The rules are public but scattered across five sources (19 CFR Part 148, the tariff schedule's Chapter 98, the TTB excise tables, the Cuba sanctions in 31 CFR Part 515, and CBP's traveller pages), and they interact in ways that catch people out. **DeclareRight** answers that question in plain language: the bottom line, the working, the facts it relied on, a citation for every rule and an as-of date, with the disclaimer that this is an estimate and the CBP officer decides.

> "4 bottles of Italian wine, 13%, $30 each, after 10 days in Italy. I'm 34 and haven't used my exemption. Do I owe anything?"
>
> **You owe $2.97 on the wine.** (abridged) 4 × 750 ml = 3 L; 1 L is duty-free, 2 L is over the allowance ($80 of value). Duty 3% = $2.40 (HTSUS 9816.00.20); federal excise 0.528 gal × $1.07 = $0.57 (TTB). Estimate as of 2026-11-21; the CBP officer decides.

## 1.2 Why a chatbot gets it wrong

Seven rules turned out different from what the project first assumed, in the business case, in the mentor's review or in CBP's own pages. Each was settled against the source text on Days 1–3 (`docs/regulatory_checks.md`, SPEC 5.5):

| Rule | First assumed (by whom) | What the regulation says |
| --- | --- | --- |
| $200 exemption (under 48 hours) | 150 ml of a 750 ml bottle is exempt, the rest dutiable (business case) | All-or-nothing: if any article is over its limit, nothing is exempt (19 CFR 148.51(b)) |
| Day trip to Mexico | $200 rules, because the trip is under 48 hours (business case and the review's corrected example) | A direct arrival from Mexico gets the $800 exemption whatever the trip length (19 CFR 148.35(a)) |
| Alcohol allowance | 1 L from any country (business case); 2 L from a list with 13 more countries, among them Peru and the Dominican Republic (CBP's older guidance) | 2 L only when arriving directly from one of the 17 beneficiary countries in HTSUS General Note 7(a), at least 1 L made there (148.33(d), Ch. 98 U.S. Note 4) |
| Tobacco over the allowance | Duty and tax can be assessed on the excess (review) | Declare it; the excess may be detained, seized or abandoned, and no duty is calculated (CBP; 19 USC 1681a). The business case's "seized, not taxed" was nearer |
| US-made export-labelled cigarettes | Can come back as "American goods returned" above the limit (business case) | Only up to the exemption; the excess can be relinquished at entry without penalty, otherwise forfeited (26 USC 5754, 5761(c)–(d)) |
| Cuban cigars bought in Cancún | Banned under OFAC FAQ 719 (business case) | Banned, but under 31 CFR 515.204 and 515.585(d); FAQ 719 covers goods acquired in Cuba |
| 3% flat rate | Always 3% (business case) | Free for goods made in a listed trade-programme country (Mexican tequila under USMCA), 4% for Column 2 countries (Russia, Belarus, Cuba, North Korea), and once per 30 days on its own (HTSUS 9816.00.20) |

Each of these is a fixed rule with a citation, not a judgement. That makes the task suit an agent whose model reads the question while code applies the rules, and it is why every rule is a row of data with its source.

## 1.3 Scope

**In scope:** returning US residents, arriving from anywhere except a US insular possession; wine (still and sparkling), beer, spirits, cigarettes and cigars, for personal use or gifts; the $800 and $200 exemptions; age; the 1 L and 2 L alcohol allowances; 200 cigarettes and 100 cigars; the flat-rate duty and TTB excise; the Cuban-origin ban; an arrival-state note for five states.

**Out of scope (a one-line scope note, no assessment):** other goods, vapes and nicotine pouches, food, cash, non-residents, crew, insular-possession arrivals ($1,600), commercial quantities, shipped goods. If other goods come with alcohol or tobacco, the alcohol and tobacco are assessed and the answer warns that the other goods share the same $800.

## 1.4 The specification

`docs/SPEC.md` (approved Day 1, template item I) fixes what the assistant must do and how correctness is judged.

- **Inputs.** A profile (age, trip length as stated, the country arrived from, exemption and flat-rate use in the last 30 days, arrival state) and a basket (per product: type, quantity as stated, size, ABV, price, origin where made, where bought, export label).
- **Outputs.** One of four outcomes: answered, clarify, refused or escalated. An answer card holds the bottom line per item (owe $X, nothing to pay, prohibited, declare with detention risk, relinquish the excess), the working, the facts relied on, any defaults used, citations from the retrieved clauses with as-of dates, the state note and the disclaimer.
- **Clarify policy (SPEC 5.2).** Ask only for facts that change the answer, all in one message, in two stages: first what decides the exemption (age, trip length, 30-day use, origin when an item could be Cuban or Russian, size, count, price), then, only when something is owed, what sets the amount (origin for the duty rate, ABV).
- **Calculation conventions (SPEC 5.1).** The $800 is applied to the highest-rate articles first, ranked by duty plus excise per litre; dutiable value rounded to the dollar, duty and excise to the cent, per line; a dutiable value over the $1,000 flat-rate band escalates.
- **Project decisions, not law (SPEC 5.4).** Commercial quantity is over 9 L of alcohol or over 12 units of one product (the law sets no line; "one case" is the common rule of thumb). The five states are New York, Florida, California, Texas and New Jersey, the busiest arrival points; the note gives the official source but no amounts.

**SPEC v2** (Day 10, for agent v2) added three rules found in testing: sake is taxed as beer, as TTB treats sake whose alcohol comes only from fermentation; the origin is asked when an item was bought in a country whose own goods pay no duty, because a local product is free and an imported one is not; and the ABV is asked in the first round when the alcohol is over the allowance whatever else is answered. Five readings settled while tuning are recorded as SPEC 9c. Agent v1 and its eval-v2 result stay under SPEC v1.

## 1.5 Rules and rates as data

`data/rules.yaml` holds the exemptions, allowances, restrictions, escalations, state notes and scope list; `data/rates.yaml` holds the flat rates by origin, the trade-programme and Caribbean Basin country lists (checked against HTSUS 2026, Revision 23), the excise rates by class and the product-name tax classes. Every row carries its citation and an as-of date (2026-11-21 for the core tables; 2026-11-22 and 2026-11-23 for the rows added later). A regulatory fix is a data change and a re-run, not a code change.

## 1.6 Constraints

| Item | Value |
| --- | --- |
| Chat model | `Qwen/Qwen3-8B` on the course endpoint; native tool calls (3 of 3) and `json_schema` output confirmed on Day 0 (`docs/endpoint_check.md`) |
| Embeddings | `bge-small-en-v1.5`, 384 dimensions, at most 512 tokens per input |
| Per call | 8,192 tokens in all, at most 1,024 output; target under 3,000 input |
| Per question | At most 10 tool steps and 12,000 tokens |
| Concurrency | One request in flight per key: every call goes through one client with a FIFO queue, back-off with jitter on 429 and 5xx, token logging and a response cache (off for official runs) |
