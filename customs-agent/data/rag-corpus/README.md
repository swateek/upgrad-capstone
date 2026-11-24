# DeclareRight RAG corpus (v2)

Official text only, one document per regulatory unit: a CFR section, a U.S. Code subsection, an HTSUS tariff line or note, an OFAC FAQ, or a section of a CBP / TTB / state page. Target 500–840 documents (CLAUDE.md, corpus); frozen as git tag `corpus-v1`.

```
rag-corpus/
├── sources.yaml        # 35 sources: kind, URL, authority, tags, split rules
├── fetch_corpus.py     # downloads -> corpus/docs/*.md, corpus/raw/*.gz, corpus/MANIFEST.json
├── chunk_corpus.py     # corpus/docs/*.md -> corpus/chunks.jsonl (350-token chunks)
└── corpus/
    ├── docs/           # one markdown file per unit, with front matter (commit)
    ├── raw/            # gzipped downloads + INDEX.json with SHA-256 (commit), and hand-saved pages
    ├── MANIFEST.json   # every doc and raw file with its hash, counts by source and authority (commit)
    └── fetch_report.json
```

## Run (from `customs-agent/`, on the Mac: government sites block the cloud workspace)

```bash
uv add pdfplumber                                        # once, for the HTSUS and CBP PDFs
uv run python data/rag-corpus/fetch_corpus.py            # about 10 minutes (1 s pause per request)
uv run python data/rag-corpus/fetch_corpus.py --check    # every doc and raw file matches MANIFEST.json
uv run python data/rag-corpus/chunk_corpus.py
```

- Re-running uses the cached raw files in `corpus/raw/`; `--refresh` downloads again; `--offline` never touches the network; `--only <source id> ...` rebuilds some sources.
- A failed source is listed in `corpus/fetch_report.json`; the rest still build.
- **Large raw files:** pre-commit refuses files over 500 KB. If a gzipped PDF is over that, add it to `customs-agent/.gitignore`; its hash stays in `MANIFEST.json`, and `--check` reports it as not committed rather than failing.
- **Freeze (Day 3):** when the counts look right, commit `corpus/` and tag `corpus-v1`. After that, a change to the corpus is a new tag and a re-run of the retrieval experiment.

## Front matter on every document

| Field | Meaning |
| --- | --- |
| `doc_id` | Unique id: `19cfr148.33`, `26usc5754-a`, `htsus9816.00.20`, `ofac-faq-719`, `cbp-duty-info--cuba` |
| `citation_id` | What the writer cites and the eval gold checks: `19cfr148.33`, `26usc5754`, `cbp-duty-info` (several docs can share one) |
| `authority` | `primary_regulation`, `agency_guidance`, `tax_rates`, `state_guidance` or `hard_negative` |
| `tags` | Topic tags for metadata filters (`alcohol`, `tobacco`, `cuba`, `crew`, `non_resident`, `off_topic`…) |
| `heading`, `title`, `source_id`, `source_url`, `as_of` | Where it came from and its effective or retrieval date |
| `raw_file`, `raw_sha256`, `text_sha256` | The snapshot it was cut from, and hashes for the freeze |

## Hard negatives

Kept so the retrieval experiment can measure confusion; filtered out before the writer and never cited:

- **19 CFR 148 Subpart G (crew members), incl. 148.64:** same 50 cigarettes / 10 cigars / 150 ml limits as the resident rule 148.51.
- **Off-topic sections of CBP pages** (pets, firearms, food, medication…): authority `hard_negative`, tag `off_topic`.
- **Food, currency (31 CFR 1010.340, FinCEN 105), visitors' rules:** whole pages marked `hard_negative`.
- Non-resident and insular-possession sections of 19 CFR 148 stay `primary_regulation` but carry `out_of_scope`.

## When a source fails

- **A page needs JavaScript or blocks scripts:** save it from a browser as `corpus/raw/<source id>.html` (or `.pdf`) and re-run; hand-saved files are used before the network. `cbp_info_cuban_cigars.html` is already saved this way.
- **HTSUS PDFs** (Chapter 98, General Notes): if the USITC file URL in `sources.yaml` fails, download the PDF from hts.usitc.gov and save it as `corpus/raw/htsus_ch98_notes.pdf` / `corpus/raw/htsus_general_notes.pdf`.
- **A parser finds nothing** (page layout changed): the error names the source; adjust its `start` / `end` / `split` in `sources.yaml`.

## Chunks (`corpus/chunks.jsonl`)

```json
{"chunk_id": "19cfr148.51#01", "doc_id": "19cfr148.51", "citation_id": "19cfr148.51", "authority": "primary_regulation",
 "heading_path": "<subpart> > § 148.51 ...", "text": "<heading path>\n\n<text>", "tokens": 212, "metadata": {...}}
```

Split on headings first (a chunk never spans two units), pack paragraphs up to 350 tokens (the embedding model takes 512), never split a table, prefix the heading path.
