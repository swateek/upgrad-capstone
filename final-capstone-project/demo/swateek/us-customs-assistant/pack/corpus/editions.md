# Edition decisions

Which edition of each source is indexed, and why. Checked against the live official sites on 17 November 2026. Hashes are in `manifest.lock.yaml`; counts per source are in `docs/results/corpus-counts.md`.

## The document unit

One document is one citable unit, the thing an answer cites:

| Source type | One document | Example citation |
|---|---|---|
| CFR | one top-level paragraph of a section; a section without lettered paragraphs is one document | 19 CFR 148.33(d) |
| US Code | one subsection | 26 USC 5001(a) |
| HTSUS | one 8-digit subheading, or one subdivision of a note | HTSUS 9816.00.20; HTSUS General Note 7(a) |
| OFAC | one FAQ | OFAC FAQ 720 |
| Web pages (CBP, TTB, states) | one heading block of the main content | CBP, Customs Duty Information — Alcoholic Beverages |

Result: **1,258 documents** (Track B range 500–2,000). Reserved paragraphs and heading-only blocks are dropped (5), and so are page footers (California's contact and campaign blocks, TTB's "Contact us").

## Decisions per source

| Source | Indexed edition | Decision |
|---|---|---|
| 19 CFR 148, 31 CFR 515, 27 CFR 27, 27 CFR 41 | eCFR point-in-time **2026-11-13** (versioner API) | The latest date eCFR offered on 17 Nov (titles 19, 27 and 31 "up to date as of 2026-11-13"). The `current` eCFR pages change daily and are excluded. All four parts are indexed whole. Most of Part 515 (other Cuba rules) and Parts 27 and 41 (bonds, permits, records) act as near-duplicate hard negatives. |
| 27 CFR 27 and 41 | as above | Added beyond the business case: they hold the **import** rate provisions. § 27.45 sets the import rates, § 27.262 covers the foreign producer's assignment of the reduced CBMA rates (rule check R8), § 41.31–41.32 set the cigar and cigarette rates, and § 41.85a covers returned US tobacco (R6). |
| 26 USC 5001, 5041, 5051, 5701, 5754, 5761 | **United States Code, 2024 edition** (govinfo) | govinfo's annual edition is static and versioned. uscode.house.gov serves the "prelim" text dynamically, with no stable file per section. Only the statute text is indexed; amendment notes are left out. |
| HTSUS Chapter 98 | **2026 HTS Revision 23** (released 10 Nov 2026), PDF | Pages 21 and 55 only: the U.S. Notes of Subchapter IV (personal exemptions) and Subchapter XVI (9816 flat rate). Pages 22–25 hold the same headings as a table, which the JSON rows give more cleanly. |
| HTSUS General Notes | **2026 HTS Revision 23**, PDF | Pages 3–4 (GN 3, rates of duty, incl. (a)(iv) insular possessions), 23–25 (GN 7, Caribbean Basin beneficiary countries, for the 2-litre rule R2) and 28–29 (GN 11 general provisions, USMCA, for R7). The hundreds of product-specific USMCA origin rules are left out. Each range opens mid-note (GN 3, 6, 10); GN 6 and GN 10 are kept as hard negatives. |
| HTSUS 9804 and 9816 rows | current HTS release, JSON (`exportList`) | USITC's JSON export has no release parameter, so these two files track the current release. On 17 Nov 2026 that was Revision 23, the same as the PDFs. The lock's text hash flags any change. |
| OFAC Cuba FAQs | live topic page, all **136 FAQs** | Static HTML; each FAQ carries its release date. FAQ 719 covers goods acquired in Cuba, and FAQ 720 covers third-country purchases, citing 31 CFR 515.585(c)–(d) (rule check R4). The rest are hard negatives about other Cuba rules. |
| TTB Tax Rates; ACE CBMA Tax Rates Table | live pages | The rate tables (2018 to present) and the import CBMA table. The rates page says importers not assigned a reduced rate pay the general rate (R8). |
| CBP traveller pages (19) | live cbp.gov pages | See the next section. |
| California | ABC page "Importing Alcoholic Beverages for Personal or Household Use" | Footer blocks dropped. |
| New York | Tax Department page "Importation for personal consumption" | The State Liquor Authority has no traveller page. The Tax Department's page carries the traveller's exemption (48-hour rule) and the personal-import limits. |
| Florida | **Florida Statutes 2025, § 562.16** | The 1-gallon exemption for beverages bought out of state and brought in by the possessor. |
| Texas | TABC "Personal Importation and Ports of Entry FAQs" | Texas's own per-person limits and state tax at ports of entry. |
| Illinois | ILCC **Form ILCC-RIA** (Request for Import Authorization), PDF | **Deviation.** The rule itself, 11 Ill. Adm. Code 100.480 on ilga.gov, could not be fetched from this machine on 17 Nov (connection timeouts on www.ilga.gov and ilga.gov). The ILCC form describes the same personal-import process. If ilga.gov becomes reachable, the rule should be added to the manifest. |

## CBP pages instead of the CBP Info Center

The plan listed "CBP traveller guidance + CBP Info Center articles (100–200 documents)". The **CBP Info Center is not fetchable**: help.cbp.gov is a Salesforce site rendered in the browser, and a plain download of an article returns only the app shell (checked 17 Nov 2026 on its sitemap's article URLs). As the plan's risk table allowed, it is excluded (`exclusions.yaml`), and these static cbp.gov pages cover the same ground:

- Core: Customs Duty Information, Types of Exemptions, For Frequent Travelers, Prohibited and Restricted Items, Shopping Abroad, Gifts, What to Expect When You Return, Your Trip, Top Ten Travel Tips, Know Before You Go: Traveling Abroad, Canada and Mexico Travel, Planning a Trip to Mexico, Clearing Customs.
- Hard negatives: Public Notice on Imports from Cuba (trade), Sending Items Back to the U.S. (shipped goods), Government/Military/Crew exemptions, Money and Monetary Instruments, Agricultural Items, Bringing Agricultural Products.

Two "Gifts" URLs serve the same page, so only one is indexed. CBP's "Know Before You Go" pocket guide is listed as print-only in the CBP publications catalogue, so it is not included.

Effect on counts: CBP web pages give 73 documents instead of the 100–200 planned. The 27 CFR parts and the OFAC FAQ page more than make up the total.

## Planned vs indexed

| Mentor's source group | Mentor's estimate | Indexed |
|---|---|---|
| 19 CFR 148 | 120–180 | 201 |
| HTSUS Ch. 98 + notes | 30–50 | 42 |
| 27 CFR TTB rate provisions + TTB tables | 40–60 | 358 (Parts 27 and 41 whole) + 5 |
| 26 USC sections | 20–30 | 32 |
| 31 CFR 515 + OFAC FAQs | 100–150 | 379 + 136 |
| CBP guidance + Info Center | 100–200 | 73 (19 cbp.gov pages; Info Center not fetchable) |
| State pages (5) | 5–10 | 23 |
| Synthetic injection fixtures | not in the table | 9 |

## Personal data

The PII scrubber redacted 26 phone numbers and 11 email addresses. All were public agency contact details on the pages (port, FDA, APHIS, CBP Info Center, OFAC), not personal data. No regulation number was affected (checked on the built documents).

## Refreshing the snapshot

`uv run python -m customs.ingest.download` re-downloads and compares text hashes with the lock. A changed source is reported, not silently accepted. After checking the change, `--freeze` updates the lock, and the rule and rate tables are re-checked before the eval runs again. Every answer shows the snapshot date (eCFR 2026-11-13, HTS Revision 23, web pages retrieved 2026-11-17).
