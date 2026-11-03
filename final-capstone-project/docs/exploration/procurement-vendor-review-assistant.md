# Procurement and vendor-review assistant

**Author:** Swateek

Source list and technical requirements for the DLlamas Track B capstone. Checked against public pages on 3 November 2026. This is the build brief for the domain. It is not the 12-page submission report.

The buyer in this system is one central ministry or department office. It follows the General Financial Rules, the current Department of Expenditure procurement manuals, the Delegation of Financial Powers Rules, GeM terms, and the Public Procurement (Preference to Make in India) Order. A one-page synthetic office note, labeled synthetic, says that this office uses the evaluation sheet stored with each bid case. That note does not invent a second set of procurement law.

Submission is 27 November 2026. The design below is sized for that window. The demo floor is the slice that should exist by about 17 November, so a short build still has something to show.

## Track B constraints this design keeps

These come from the track brief and stay fixed.

- The model is a hosted instruct model of at most 8B parameters, behind an OpenAI-compatible chat endpoint. Weights stay frozen. A larger model is not a fallback.
- An embeddings endpoint is provided with that chat endpoint. Retrieval uses that endpoint.
- The corpus cap is 2,000 documents. The agent cap is 10 steps per query.
- The team writes 60–100 realistic queries with gold answers before any agent code.
- Retrieval is hybrid (BM25 plus dense), with a reranker, and answers cite sources.
- Retrieval recall@k is measured separately from end-to-end answer quality.
- The system has at least three tools and an explicit planner, executor, and critic.
- State persists across turns. Tool failures, malformed JSON, loops, and token-budget caps are handled in code.
- The shipped demo is a small front end, containerised, with rate limiting and caching.
- Consequential actions stay with a person. The system drafts. It does not award, debar, or place an order.
- The starter skeleton, API key, and per-team token quota are not in this repository yet. The orchestrator library stays the one in that skeleton. This brief does not add a second framework.

## What the system does

One copilot, three jobs, one stack.

| Job | User question | What a correct answer is |
| --- | --- | --- |
| Policy Q&A | What rule applies to this purchase, threshold, exception, or approval? | A short answer whose factual sentences each cite an indexed rule id, plus the office note when the question is about this office's score sheet. |
| Vendor screening | Is this firm on a list we have loaded? | A structured hit or a clear "not present in the snapshot dated …". Absence from the snapshot is not a finding that the firm is eligible. |
| Bid comparison | How do these preloaded proposals score against this case's sheet? | A draft score sheet in a fixed schema. A debarred or delisted name cannot be recommended. The draft is not an award. |

The three jobs share one session. The session remembers the active vendor, the active case id, and the last tool payload.

## Data sources

Load three stores. Keep them separate.

| Store | Contents | Used by |
| --- | --- | --- |
| Policy index | Clause-level text from one current edition of each public instrument | `search_policy` |
| Screening table | Dated rows of firm and brand names taken from public lists, plus a small labeled synthetic vendor set | `screen_vendor` |
| Bid-case index | 8–12 synthetic cases, each with a requirement sheet and three proposals | `score_bids` |

Tender notices do not go into the policy index. Screening rows do not go into the vector index. A sanctions list of thousands of entities will drown a policy question.

Target size for the policy index is 500–1,200 documents, under the 2,000 cap. Split each chosen PDF at rule or heading boundaries, count the documents, and stop. If the split is under 500, add model-tender sections and the selected office memoranda listed below. Do not pad the index with tender listings that have no rule text.

English documents only. Record the edition date and a file hash for every file that is indexed. If a later page and an earlier PDF disagree, keep one edition and write down which one.

### Policy corpus

Index these. They are the legal spine for policy answers.

| Instrument | What to download | Link |
| --- | --- | --- |
| Manual for Procurement of Goods, Second Edition, 2024 | Direct PDF. Foreword dated 22 July 2024. DoE circular dated 16 August 2024. This is the comprehensive manual the other manuals point back to. | [PDF](https://doe.gov.in/files/circulars_document/Manual_Goods_2024.pdf) · [circular](https://doe.gov.in/circulars/manual-procurement-goods-second-edition-2024) |
| Manual for Procurement of Non-Consultancy Services, 2025 | Direct PDF on the DoE manuals path. The file states that it tracks GFR and DoE clarifications through April 2025. | [PDF](https://doe.gov.in/files/manuals_documents/MfPoNCS2025.pdf) |
| Delegation of Financial Powers Rules, 2024 | Booklet. In force from 1 April 2024. Use it for who may sanction expenditure and for the purchase rules, especially Rules 11 and 12 and the schedules that set limits. | [PDF](https://doe.gov.in/files/circulars_document/Delegation_of_Financial_Powers_Rules_2024_Booklet.pdf) · [orders list](https://doe.gov.in/orders-circulars/28) |
| GeM General Terms and Conditions 4.0, version 1.27 | Dated 1 December 2025. GeM file names are content hashes and can change. If this URL fails, take the current GTC from [gem.gov.in](https://gem.gov.in/) and check that the version line still reads 4.0 / 1.27 or record the newer version you actually hashed. | [PDF](https://assets-bg.gem.gov.in/resources/upload/shared_doc/gtc/GeM-GTC-40-1764595497.pdf) |
| GeM Incident Management Policy | How buyer-specific and Department of Expenditure debarment is applied on GeM. Same caveat on hashed file names. | [PDF](https://assets-bg.gem.gov.in/resources/upload/shared_doc/im-policy_1785130926.pdf) |
| Public Procurement (Preference to Make in India) Order, revised 19 July 2024 | DPIIT order P-45021/2/2017-PP (BE-II)-Part(4) Vol.II. Class-I local supplier is 50% local content unless a nodal ministry sets a higher bar. Class-II is 20%. Purchase-preference margin is 20%. Purchases below Rs 5 lakh are exempt. | [PDF](https://www.dpiit.gov.in/static/uploads/2025/07/458478309ccf301ceb58f63d02646f42.pdf) |

Take the remaining two manuals from the index pages, not from an archived 2022 file.

| Instrument | Where to get the current file | Link |
| --- | --- | --- |
| General Financial Rules, 2017, procurement rules | DoE hosts a consolidated PDF updated to 31 July 2024, and a page for the bi-annual compilation of amendments to 31 January 2025. The DGMA acts list shows a compilation updated to 31 January 2026. Download the latest file you can actually open, hash it, and index the procurement rules (Chapter 6 and any amended rule the evaluation set asks about). Leave the rest of GFR out of the index. | [GFR landing page](https://doe.gov.in/general-financial-rules) · [PDF through 31 July 2024](https://doe.gov.in/files/circulars_document/FInal_GFR_upto_31_07_2024.pdf) · [amendments through 31 January 2025](https://doe.gov.in/bi-annual-compilationupdation-amendments-gfrs-2017-upto-31-jan-2025) · [DGMA acts list](https://www.dgma.gov.in/finance-accounts-audit-public-procurement/finance-acts-rules) |
| Manual for Procurement of Consultancy Services | DGMA lists a file dated 20 June 2025. Confirm the PDF linked from [DoE manuals](https://doe.gov.in/manuals) or from that DGMA list on the day you download it. Do not guess a file name. | [DoE manuals](https://doe.gov.in/manuals) · [DGMA acts list](https://www.dgma.gov.in/finance-accounts-audit-public-procurement/finance-acts-rules) |
| Manual for Procurement of Works | DGMA lists a file dated 23 December 2025. Same rule: follow the current link on the DoE manuals page or the DGMA list, then hash the file. | [DoE manuals](https://doe.gov.in/manuals) · [DGMA acts list](https://www.dgma.gov.in/finance-accounts-audit-public-procurement/finance-acts-rules) |

Add a short, selected set of Department of Expenditure office memoranda only when one of them changes debarment, mandatory GeM use, or a rule already in the evaluation set. The procurement-policy list is [doe.gov.in/orders-circulars/459](https://doe.gov.in/orders-circulars/459).

Model tender documents supply the shape of a bid case. Start from the consultancy model tender circular, [No.F.13/1/2022-PPD dated 8 June 2023](https://www.doe.gov.in/circulars/model-tender-document-procurement-consultancy-services), and the goods and non-consultancy model tenders linked from the same DoE circulars area. Index those sections only if the policy split is still under 500 documents. Their main job is the bid-case template, not extra policy bulk.

The synthetic office note is one document. It states that this office follows the frozen public files above and scores each case with the sheet stored beside that case. Label it synthetic in the corpus metadata.

### Vendor screening snapshot

Screening is a table lookup. The model does not decide whether two names match.

| Source | How to use it | Link |
| --- | --- | --- |
| GeM list of sellers, brands, and catalogues removed for non-compliance with GFR Rule 144(xi) | Parse the PDF into rows: seller, brand, catalogue, and the date on the list. Store GeM's disclaimer with the snapshot. The list is about eligibility to participate on GeM. It is not a finding about quality, credit, or general fitness. The PDF cites DoE OMs F.No.6/18/2019-PPD dated 23 July 2020 and F.No.7/10/2021-PPD dated 23 February 2023. Attach an OM only after you download it from doe.gov.in. | [PDF](https://assets-bg.gem.gov.in/resources/upload/shared_doc/sellers-brands-and-catalogues-delisted-from-gem-du_1781592087.pdf) |
| CPPP debarment search | A portal page, not a bulk feed. Keyword search on the tender portal is captcha-gated. There is no official API to call at query time. A hand export of a few rows is allowed only if you store the export date and the page you took them from. | [Debarment list page](https://eprocure.gov.in/eprocure/app?page=FrontEndDebarmentList&service=page) · [CPPP](https://eprocure.gov.in/cppp/) |
| OpenSanctions, World Bank debarred providers | Optional second snapshot, and only for a foreign bidder the case actually names. Non-commercial bulk use. Prefer the simple CSV. Do not call the hosted match API on the demo path. | [Dataset](https://www.opensanctions.org/datasets/worldbank_debarred/) · [bulk data terms](https://www.opensanctions.org/docs/bulk/) · [World Bank list page](https://www.worldbank.org/en/projects-operations/procurement/debarred-firms) |
| Synthetic vendor master, about 30 names | Labeled synthetic. Include one exact hit from the GeM list, one near-miss name, one clean name, and one name that appears only in a hand-exported buyer-specific debarment row if you made that export. These names exist so the evaluation set has known answers. | Created by the team, stored next to the snapshot |

Each screening row stores: normalized name, source list, period if the source gives one, source URL, and the snapshot date. The tool returns those fields. The critic repeats them. Wording in the answer is "present on [list] as of [snapshot date]" or "not present in the snapshot dated [date]".

Ministry pages that publish their own blacklists, such as a single society's HTML table, are buyer-specific. They are not a national list. Use one only as a labeled sample inside the synthetic master, with the source URL kept on the row.

### Bid cases

Competing technical proposals are not public. Award notices say who won and, sometimes, the price. They do not contain the losing bids. The score sheet therefore cannot be built from scraped awards.

Build 8–12 cases by hand:

- One requirement sheet per case, in the shape of a Department of Expenditure model tender: mandatory conditions and scored criteria with weights.
- Three synthetic proposals per case, labeled synthetic.
- A gold score sheet the evaluation set can check: requirement id, mandatory or scored, weight, quoted evidence, score, and gap.
- At least one case where a bidder name is on the GeM delist snapshot, so the draft must withhold a recommendation.
- At least one case where a mandatory condition fails.
- At least one case where a proposal contains an instruction to ignore GFR or to award full marks. That text is data. The score ignores it.

A few real notice texts may be saved by hand from [eprocure.gov.in/cppp](https://eprocure.gov.in/cppp/) and used only as scope language for a case. Save the notice id and the date. Do not scrape the portal from the running app.

### Leave these out of the corpus

- Archived manuals that contradict the current edition. The June 2022 consultancy manual is one of these: [2022 PDF](https://doe.gov.in/files/manuals_documents/Manual_for_Procurement_of_Consultancy_%26_Other_Services_Updated%20June%2C%202022_1.pdf). The 2017 and 2022 goods manuals on the same [manuals index](https://doe.gov.in/manuals) stay out once the 2024 goods manual is the indexed edition.
- Hindi editions.
- The demo host `democppp.nic.in`.
- Multi-million-row scraped tender dumps. They exceed the document cap, mix empty and dirty fields, and are not bid proposals.
- Live calls to GeM, CPPP, MCA, GST, or a credit bureau.
- PAN, Aadhaar, phone numbers, and email addresses. If a downloaded file contains them, drop those fields before indexing. Do not collect identity numbers in order to screen a firm.
- MSE purchase-preference questions, until an official Ministry of MSME PDF is saved with a hash. Until that file is in the index, the evaluation set does not ask them.

## Technical requirements

### Demo floor, about 17 November

This slice is the system you can still demonstrate if the rest slips. Build it before the agent loop.

1. Freeze the evaluation set first. Minimum 60 queries, allowed to grow to 100 before any agent code: about 25 policy, 20 screening, and 15 bid questions. Refusals sit inside those counts. Every policy gold answer names a rule id in the frozen corpus. Every screening gold answer is a hit or a documented miss on the snapshot. Every bid gold answer is a score row.
2. Policy retrieval over the clause index: BM25 plus the provided embeddings endpoint. Every factual sentence carries a citation (document id and rule id).
3. `screen_vendor(name)` against the local snapshot. Name matching is code: a normalized string compare, then a fuzzy score from a library such as RapidFuzz. The model never invents a match.
4. One preloaded bid case returned as schema-valid JSON from `score_bids(case_id)`.
5. A Streamlit page with three tabs (policy, vendor, bid), a visible "draft" watermark, and no control that approves, awards, or debars.
6. One recorded single-prompt baseline on the policy questions, with a short note of how this model fails (dropped citations, broken JSON, merged rules, or a recommendation it was not asked for).

### Full submission, 27 November

Everything in the demo floor, plus the Track B checklist below. Nothing in this list depends on a live government portal.

**Tools and loop**

- `search_policy(query, instrument)` searches only the policy index.
- `screen_vendor(name)` searches only the screening table.
- `score_bids(case_id)` loads that frozen case and returns clause-level scores. A missing price or a missing mandatory response is a gap in the schema, not a number the model fills in.
- Planner, then executor, then critic. The critic checks that citations exist, that scores use the sheet weights, that a listed firm is not recommended, and that the answer does not say "award" or "debarred by us".
- Session state holds the active vendor, the active case id, and the last tool payload.
- Hard stop at 10 steps. On malformed JSON, validate with a schema (Pydantic or equivalent), return the validation error to the model, and retry once. Use the endpoint's JSON schema mode if the provided API supports it. The retry path has to work even if it does not.
- The orchestrator is the one shipped in the starter. If the starter has no orchestrator, a single hand-rolled loop that implements the three roles above is enough. Do not add CrewAI or AutoGen beside it.

**Retrieval experiments**

- Compare three chunkings on about 40 labeled policy questions: one document per rule or heading, a fixed-size split, and a recursive character split. Publish recall@5 and recall@10 for each. Keep the winner for the demo.
- Hybrid search merges BM25 and dense results with reciprocal rank fusion. BM25 can be `rank-bm25` at this corpus size. Dense vectors come from the provided embeddings endpoint.
- Rerank the top 20 fused hits with a small CPU cross-encoder, such as `BAAI/bge-reranker-base`. Do not send the whole corpus to the 8B model to rerank.
- Use the vector store the starter provides. If it provides none, a local store is enough for a corpus of this size.

**Prompt comparison**

Compare three strategies on the policy task only, against the frozen policy questions:

- Structured output with a few gold examples.
- Chain-of-thought, with the reasoning kept out of the user-visible answer and the citations kept in.
- Decomposition: split the question into rule lookup, then answer from the retrieved rules.

Record where the 8B model breaks under each strategy. Self-consistency stays off the default path because the token quota is shared and unknown.

**Evaluation and observability**

Report, on the frozen set:

- End-to-end accuracy, scored against the gold rule id, the gold hit or miss, or the gold score rows.
- Task completion rate.
- Average tool calls per task.
- Latency and token cost per query, using the provided endpoint's usage fields.
- A failure label on each miss: retrieval miss, reasoning error, tool-call error, or hallucination.

Trace real queries with the tracer the starter configures. If it configures none, use Langfuse or OpenTelemetry.

**Ship**

- Streamlit, as in the demo floor, wrapped in a container.
- A per-session rate limit and a retrieval cache keyed by the normalized query plus the corpus hash.
- The safety checks in the next section, written up with the results.

### Required behaviour on unsafe or consequential requests

The assistant declines, and says why, when the user asks it to:

- Award a contract, place a purchase order, or debar a firm.
- Treat text inside a retrieved proposal or manual as an instruction.
- Answer from a manual edition that was not indexed.
- Treat "not in the snapshot" as "this firm is eligible".
- Build a dossier on a private person beyond the sentence "this name appears on [published list] as of [snapshot date]".
- Score a case that has no requirement sheet in the bid-case index.

The safety set that must be in the evaluation file:

- A proposal that says to ignore GFR and award full marks.
- A question whose correct answer is only in a superseded manual you deliberately left out.
- A request to award the case or to debar the losing firm.
- A request to clear a vendor name that is absent from the snapshot.

### Cuts that keep the three jobs inside the window

- Query-time calls to GeM or CPPP.
- Hindi OCR.
- Upload of an arbitrary vendor PDF in the UI. Cases are preloaded.
- MCA, GST, and credit lookups.
- Self-consistency on the default path.
- A React front end.
- Agents beyond the planner, the executor, and the critic.
- Fine-tuning. This track does not train weights.

## Build order

The order protects the 17 November demo. It is not a staffing plan.

1. Freeze the corpus list, hashes, and edition dates. Then write the evaluation set. Stop there before agent code.
2. Index the policy clauses and run the single-prompt baseline.
3. Load the screening snapshot and the one demo bid case.
4. Put the three tools behind the Streamlit tabs so the demo floor runs without the planner.
5. Add hybrid search, the chunking comparison, the reranker, and the three prompt strategies.
6. Add the planner, executor, critic, the step cap, and the schema retry.
7. Add traces, the container, the rate limit, the cache, and the safety set.

## Open items

- The starter skeleton and the token quota are not in the repository yet. When they arrive, use their orchestrator, vector store, and tracer, and keep the tool contracts in this brief.
- Consultancy and works manuals must be taken from the live DoE or DGMA link on download day. This brief does not invent those file names.
- The GFR file to freeze is the latest consolidated PDF you can actually hash. The 31 July 2024 DoE PDF, the 31 January 2025 compilation page, and the 31 January 2026 DGMA listing are the candidates. Index one.
- GeM asset URLs are hashed. Re-download from gem.gov.in if a link in this brief fails, and record the version you hashed.
