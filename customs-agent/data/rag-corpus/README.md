# Customs assistant RAG corpus: alcohol & tobacco (v1)

The source documents for the assistant's `retrieve` tool, plus the scripts that download, check and chunk them.

```
rag-corpus/
├── sources.yaml            # the 14 sources (13 + 1 hard negative): URL, authority, tags, sections
├── fetch_corpus.py         # downloads official text -> corpus/primary/*.md
├── chunk_corpus.py         # corpus/**/*.md -> corpus/chunks.jsonl
└── corpus/
    ├── primary/            # filled by fetch_corpus.py (commit the output)
    └── raw/                # optional: manually saved HTML/PDF used before the network
```

## Quick start

Run from `customs-agent/` (dependencies are managed with uv there; add them once):

```bash
uv add requests pyyaml beautifulsoup4 lxml markdownify
uv add --optional pdf pdfplumber      # only for the HTSUS Chapter 98 PDF
uv run python data/rag-corpus/fetch_corpus.py   # writes corpus/primary/ and corpus/fetch_report.json
uv run python data/rag-corpus/chunk_corpus.py   # writes corpus/chunks.jsonl (350-token chunks)
```

Commit `corpus/primary/` so everyone indexes the same snapshot. Re-run `fetch_corpus.py` weekly and review the git diff: a changed line in a regulation is the signal to update the rule tables.

## What goes in, and why

| Group | Sources | Authority | Used for |
| --- | --- | --- | --- |
| Regulations | 19 CFR 148.31-148.39 ($800 exemption), 148.51 ($200), 148.101+ (flat rate); 31 CFR 515.204, 515.560, 515.585 (Cuba) | `primary_regulation` | The citation shown to the traveller |
| Tariff schedule | HTSUS 9804.00.65-.72, 9816.00.20-.40, Chapter 98 Subchapter IV U.S. Notes | `primary_regulation` | Exemption headings, flat rate, quantity limits |
| CBP guidance | Customs duty information; Types of exemptions; Prohibited and restricted items; Info Center: Cuban cigars | `agency_guidance` | Plain-language explanations, examples, state-law and seizure rules |
| OFAC | FAQ 719, FAQ 769 | `agency_guidance` | Cuban alcohol and tobacco ban since 24 Sep 2020 |
| TTB | Excise tax rates page (alcohol and tobacco on one page) | `tax_rates` | Citations for excise; the numbers themselves live in the rule tables |

## Hard negatives and exclusions

- **19 CFR 148 Subpart G (crew members), including 148.64: kept as a hard negative.** It has the same 50 cigarettes / 10 cigars / 150 ml limits as the $200 resident rule, so it tests whether retrieval picks the right section. It is tagged `crew` with authority `hard_negative`: filter it out for travellers and never cite it.
- **Insular-possession ($1,600) and non-resident rules.** Out of scope for v1.
- **Third-party sites and HTS mirrors.** Not authoritative.

## When a fetch fails

The script keeps going and lists failures in `corpus/fetch_report.json`.

- **cbp.gov blocks scripts** (common): open the page in a browser, save it as HTML to `corpus/raw/<id>.html` (id from `sources.yaml`), and re-run. Saved files are used before the network.
- **HTSUS Chapter 98 notes:** download the Chapter 98 PDF from hts.usitc.gov, save it as `corpus/raw/htsus_chapter98.pdf`, and re-run. The script extracts Subchapter IV into `corpus/primary/htsus_ch98_subchapter4_notes.md`.
- **HTS API shape changed:** the `exportList` endpoint is the one the USITC site uses; if it errors, save the 9804 and 9816 lines from the website as text into `corpus/primary/` with the same front matter.

## Chunk format

One JSON object per line in `corpus/chunks.jsonl`:

```json
{
  "chunk_id": "19cfr148_51_200_exemption#002",
  "doc_id": "19cfr148_51_200_exemption",
  "heading_path": "19 CFR 148.51 ... > § 148.51 Special exemption for personal or household articles.",
  "text": "<heading path>\n\n<chunk text>",
  "tokens": 212,
  "metadata": {"authority": "primary_regulation", "source_url": "...", "tags": ["exemption_200", "..."], "effective_as_of": "2026-10-08", "fetched_at": "..."}
}
```

Rules the chunker follows: split on headings first, so a chunk never spans two CFR sections; pack paragraphs up to 350 tokens; never split a table; prefix the heading path so a chunk makes sense alone.

## How `retrieve` should use it

- Return the top 3 chunks, 350 tokens each, so a stage's prompt stays well under the 8,192-token call limit.
- Filter by `tags` from the traveller profile (for example `short_trip` → `exemption_200`) before ranking.
- Rank `primary_regulation` above `agency_guidance` on ties.
- Never return `hard_negative` chunks to the writer; they exist to measure whether retrieval confuses the crew rule (148.64) with the resident rule (148.51).
- The writer may cite only `primary_regulation`, `agency_guidance` or `tax_rates` chunks. The corpus is official text only.

## Spot-check after the first fetch (domain spec owner)

Search the fetched files and confirm each figure appears in a primary or agency source:

- [ ] 1 liter of alcohol inside the $800 exemption, age 21+
- [ ] 200 cigarettes and 100 cigars inside the $800 exemption
- [ ] $200 exemption: 50 cigarettes, 10 cigars, 150 ml alcohol; no family pooling
- [ ] 48 hours abroad; not used in the previous 30 days
- [ ] Flat rate 3% under 9816.00.20
- [ ] Extra alcohol: flat rate plus excise, even under $800
- [ ] Extra tobacco: detention, seizure, penalties
- [ ] Caribbean Basin / Andean: 2 liters if 1 liter produced there
- [ ] Cuban alcohol and tobacco barred as baggage since 24 Sep 2020
- [ ] TTB: spirits $13.50 per proof gallon; wine up to 16% ABV $1.07 per gallon; cigarettes $50.33 per 1,000

