# Logistics Operations RAG Assistant — Design Document

| Field | Value |
| --- | --- |
| Assignment | RAG Assignment: Logistics Operations Assistant |
| Organisation (fictional) | AeroVelo Logistics Global |
| Document status | Proposed design for implementation |
| Implementation notebook (modify in place) | [`../results/Logistics_Operations_RAG_Assistant_Starter.ipynb`](../results/Logistics_Operations_RAG_Assistant_Starter.ipynb) |
| Dataset root | [`../dataset/`](../dataset/) |
| Brief (source of marks) | [`../../dumps/practice-capstone-project/RAG Assignment-Logistics Operations Assistant.pdf`](../../dumps/practice-capstone-project/RAG%20Assignment-Logistics%20Operations%20Assistant.pdf) |

This document is the build guide for the practice assignment. It maps every graded checkpoint, locks model and pipeline choices, records corpus facts that affect retrieval, and states submission constraints.

**Implementation rule:** The starter notebook already exists at [`practice-capstone-project/results/Logistics_Operations_RAG_Assistant_Starter.ipynb`](../results/Logistics_Operations_RAG_Assistant_Starter.ipynb). That file is the sole implementation artifact. Fill its empty code cells, keep its markdown section structure and mark headings, and produce runnable outputs there. Do not create a parallel notebook for the graded work unless renaming a completed copy for LMS submission (see Section 7).

---

## 1. Objective and business value

### 1.1 Objective

Design and implement a Retrieval-Augmented Generation (RAG) workflow for AeroVelo Logistics Global. Given an operational question, the assistant retrieves relevant passages from the supplied documents and generates an answer grounded in that context.

The graded workflow covers:

1. Load and analyse the ten documents.
2. Create overlapping chunks and preserve metadata.
3. Build a persistent vector database.
4. Connect a language model with a grounded prompt.
5. Evaluate five supported questions and one unsupported question.
6. Display retrieved filenames and report limitations.

### 1.2 Business value

Operations teams search across supplier policies, incident procedures, financial authorisation rules, and compliance documents. A document-grounded assistant reduces manual searching and returns consistent information from the available sources. Displaying retrieved filenames supports traceability. A clear response when information is unavailable reduces unsupported claims.

This assignment provides information only. It does not execute business transactions, place orders, update incident registries, or connect to live logistics systems.

### 1.3 Success criteria (aligned to 100 marks)

| Area | Marks | Outcome required |
| --- | ---: | --- |
| Data loading, preparation, and analysis | 40 | All 10 documents loaded with metadata; cleaned text; length, frequency, and TF-IDF analysis; overlapping chunks with metadata |
| Vector database and RAG chain | 35 | MiniLM embeddings; Chroma `logistics_rag`; retriever + prompt + LLM; answers with source filenames |
| RAG evaluation | 20 | Five paired questions; answer and retrieval similarity; averages; unsupported-question test |
| Conclusion | 5 | Findings, limitations, and one practical improvement supported by observed outputs |

Grading focuses on implementation, relevant retrieval, supported answers, traceability, and interpretation. Exact phrase matching with the language model is not required.

---

## 2. Locked decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| Language model | `meta-llama/Llama-3.2-3B-Instruct` via Hugging Face Inference (Featherless) | Instruct checkpoint corresponding to the brief’s `llama3.2:3b`; non-reasoning model suitable for short grounded answers |
| Local Ollama | Not used | Replaced by the Hugging Face hosted endpoint |
| Gemini | Not used | Optional alternative in the brief; out of scope for this design |
| build.nvidia | Not used | Catalog checked 7 Oct 2026 did not list `llama3.2:3b`; hosted text models there are mostly reasoning or multimodal |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` | Explicit graded requirement (checkpoint 2.1.1); also used for answer and retrieval similarity |
| Vector store | Persistent Chroma, collection name `logistics_rag` | Explicit graded requirement |
| Chunk size / overlap | 800 characters / 120 characters | Explicit graded requirement |
| Retrieval depth | `k = 4` | Explicit graded requirement |
| Generation temperature | Equivalent of temperature 0 (`do_sample=False`, and `temperature=0` when accepted) | Explicit graded requirement |
| Base Llama weights | `meta-llama/Llama-3.2-3B` not used | Base checkpoint is not instruction-tuned for Q&A |
| Python environment | Project-local virtual environment `.venv` | Isolates assignment packages; do not commit the directory |
| Implementation notebook | Modify [`../results/Logistics_Operations_RAG_Assistant_Starter.ipynb`](../results/Logistics_Operations_RAG_Assistant_Starter.ipynb) in place | Starter already present; fill its cells; retain section structure |

---

## 3. System architecture

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  dataset/  (10 files: 9 Markdown + 1 PDF)                                │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ load + metadata
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Clean / normalise whitespace (meaning preserved)                        │
└───────────────┬───────────────────────────────┬──────────────────────────┘
                │                               │
                ▼                               ▼
┌───────────────────────────┐     ┌────────────────────────────────────────┐
│  EDA                      │     │  CharacterTextSplitter                 │
│  lengths, word freq,      │     │  chunk_size=800, chunk_overlap=120     │
│  TF-IDF cosine matrix     │     │  metadata copied to each chunk         │
└───────────────────────────┘     └─────────────────┬──────────────────────┘
                                                    │ MiniLM embeddings
                                                    ▼
                                      ┌──────────────────────────┐
                                      │  Chroma: logistics_rag   │
                                      │  (delete + recreate)     │
                                      └─────────────┬────────────┘
                                                    │ top-4 retrieve
                                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Context formatter → grounded prompt → ChatHuggingFace (Llama 3.2 3B)    │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Answer + retrieved filenames                                            │
│  Evaluate: answer similarity + retrieval similarity (MiniLM cosine)      │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Component map

| Component | Technology | Notes |
| --- | --- | --- |
| Document loaders | LangChain community Markdown / PDF loaders (`pypdf`) | Walk `dataset/` recursively; keep folder structure |
| Cleaning | Custom whitespace normalisation | Collapse runs of whitespace; preserve headings, tables, numbers, and document IDs |
| EDA | `pandas`, NLTK stop words, `sklearn` TF-IDF + cosine | See Section 6 |
| Chunking | `RecursiveCharacterTextSplitter` or equivalent character splitter | Size 800, overlap 120 |
| Embeddings | `HuggingFaceEmbeddings` / sentence-transformers | `all-MiniLM-L6-v2` |
| Vector DB | `langchain-chroma` / Chroma | Collection `logistics_rag`; persistent directory |
| LLM | `langchain-huggingface` | `HuggingFaceEndpoint` + `ChatHuggingFace` |
| Evaluation | Same MiniLM encoder | Cosine similarity for answer and retrieval scores |

---

## 4. Dataset inventory

### 4.1 Location and layout

The brief asks for the dataset ZIP extracted into a `dataset` folder beside the notebook. In this repository the notebook will live under `practice-capstone-project/results/` (so cell outputs are kept by the existing `nbstripout` exclude). The loader therefore uses:

```text
DATASET_DIR = Path("..") / "dataset"   # relative to the notebook in results/
```

That path already contains the eight business folders and all ten files. Do not flatten folders. Do not embed the full dataset in the notebook.

### 4.2 File catalogue (exactly 10)

| # | Relative path | Category | Type | Document ID / topic |
| ---: | --- | --- | --- | --- |
| 1 | `compliance/SOP-COM-015_Regulatory_Breach_Report.md` | compliance | md | SOP-COM-015 — regulatory breach reporting |
| 2 | `finance/FIN-AUTH-101_Authorization_Framework.md` | finance | md | FIN-AUTH-101 — spending and emergency procurement |
| 3 | `governance/RGM-2026_Regional_Governance_Matrix.md` | governance | md | RGM-2026 — regional governance matrix |
| 4 | `hr/HR-POL-030_Remote_Work_US.md` | hr | md | HR-POL-030 — US remote work |
| 5 | `hr/HR-POL-030-EMEA_Remote_Work.md` | hr | md | HR-POL-030-EMEA — EMEA remote work |
| 6 | `legal/LEG-GDPR-007_Supplier_Data_Processing.md` | legal | md | LEG-GDPR-007 — supplier personal data processing |
| 7 | `operations/OP-204_Incident_Management_v4.md` | operations | md | OP-204 — incident management |
| 8 | `pdfs/RGM-2026_Regional_Governance_Matrix.pdf` | pdfs | pdf | RGM-2026 — PDF copy of the governance matrix |
| 9 | `supply_chain/AVL-PUR-012_Supplier_Qualification.md` | supply_chain | md | AVL-PUR-012 — supplier qualification |
| 10 | `supply_chain/BOM-FLT-H2NEX.md` | supply_chain | md | BOM-FLT-H2NEX — H2-Nexus bill of materials |

### 4.3 Content overlap: RGM Markdown and PDF

The regional governance matrix is supplied in both Markdown and PDF. Both files must be loaded. Consequences for the pipeline:

- TF-IDF cosine similarity between the Markdown and PDF versions is expected to be high.
- Retrieval for governance questions may return both files inside the top 4, which reduces diversity of other sources.
- Deduplicating them would drop a required file and is therefore out of scope for the graded notebook. Treat duplicate hits as a documented limitation and as a candidate practical improvement in the conclusion (for example, prefer Markdown when content hashes match, or diversify retrieval).

### 4.4 Documents cited but absent from the dataset

| Citation | Where referenced | Implication |
| --- | --- | --- |
| AVL-BUD-2026 | FIN-AUTH-101 | Annual budget figures are unavailable — use for the unsupported question |
| AVL-ORG-001 | RGM-2026 | Organisation chart not in corpus |
| AVL-LEG-001 | SOP-COM-015 | Legal privilege / retention policy not in corpus |

### 4.5 Cross-document conflicts (do not reconcile in answers)

When both sources appear in retrieved context, the grounded prompt must prefer quoting what the context says and acknowledging conflict rather than inventing a single “correct” company rule.

| Topic | Source A | Source B |
| --- | --- | --- |
| Regional VP monthly cumulative limit | FIN-AUTH-101 Table 1: `$500,000` | RGM-2026 Table 2B: `$400,000` |
| Hub Operations Manager monthly limit | FIN-AUTH-101 Table 1: `$20,000` | RGM-2026 Table 2B: `$25,000` |
| Emergency procurement section reference | LEG-GDPR-007 and BOM-FLT-H2NEX cite “FIN-AUTH-101 Section 3” | In FIN-AUTH-101, Section 3 is budget variance; emergency brackets are Table 2 under Section 2 |
| Incident-related financial resolution | FIN-AUTH-101 Section 5 cites “Section 3.1 of SOP OP-204” for authority levels | OP-204 Section 3.1 is the tier definition table, not a spending matrix |

---

## 5. Runtime, packages, and secrets

### 5.1 Python virtual environment (`.venv`)

All Python dependencies for this assignment are installed and run inside a project-local virtual environment named **`.venv`**, created at the repository root (or at `practice-capstone-project/` if the team prefers a scoped env). The notebook kernel and any shell install commands must use that environment so package versions do not collide with system Python.

Recommended setup (run once before filling the notebook):

```bash
# from the repository root
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install pandas matplotlib tqdm pypdf nltk scikit-learn \
  langchain langchain-core langchain-community \
  langchain-text-splitters langchain-huggingface langchain-chroma \
  sentence-transformers ipykernel
python -m ipykernel install --user --name=upgrad-capstone-venv --display-name="Python (.venv upgrad-capstone)"
```

Rules:

- Select the `.venv` kernel (or the registered `Python (.venv upgrad-capstone)` kernel) in Jupyter / VS Code / Cursor before running cells.
- Prefer installing packages with the activated `.venv` rather than `!pip` against a different interpreter. If the notebook uses install cells, they must target the same `.venv` interpreter.
- Do **not** commit `.venv/` to git. It holds local binaries, downloaded wheels, and site-packages; recreate it from the install list above (or a future `requirements.txt` if one is added).
- NLTK data and the MiniLM model cache may live under the user cache directories or inside the environment; either is fine as long as the notebook documents the assumption. Do not commit large model cache directories.

### 5.2 Required packages

Install into `.venv` (commented install cells in the starter notebook are acceptable if they use that environment). The starter’s “Loading libraries” cell currently comments `# !pip install -U -q langchain-ollama`. **Edit that cell:** remove the Ollama line and ensure installs match the list below (Hugging Face chat uses `langchain-huggingface`, which is already listed for embeddings).

```text
pandas matplotlib tqdm pypdf nltk scikit-learn
langchain langchain-core langchain-community
langchain-text-splitters langchain-huggingface langchain-chroma
sentence-transformers
ipykernel
```

Do **not** install:

- `langchain-ollama` (present as a commented line in the starter — delete it)
- `langchain-google-genai`
- `langchain-nvidia-ai-endpoints`

Optional: `matplotlib` is listed in the starter for charts (for example a length bar chart). Visualisation is helpful but not a separate mark; length/frequency/TF-IDF tables satisfy the graded asks.

### 5.3 Hugging Face access

| Item | Value |
| --- | --- |
| Model repo | `meta-llama/Llama-3.2-3B-Instruct` |
| License | Llama 3.2 Community License (gated: manual accept on the model page) |
| Token env var | `HUGGINGFACEHUB_API_TOKEN` |
| Inference provider | `featherless-ai` (only live provider mapping as of 7 Oct 2026) |
| Provider task | `conversational` |

Setup steps before a graded run:

1. Create a Hugging Face account.
2. Open `https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct` and accept the license.
3. Create an access token with permission to call Inference Providers.
4. Export `HUGGINGFACEHUB_API_TOKEN` in the environment, or prompt once with `getpass` in a local session.
5. Never hard-code the token in the notebook or commit it to git.

### 5.4 LLM construction (design contract)

```python
from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace

endpoint = HuggingFaceEndpoint(
    repo_id="meta-llama/Llama-3.2-3B-Instruct",
    task="text-generation",
    provider="featherless-ai",
    max_new_tokens=512,
    do_sample=False,
    temperature=0,
)
llm = ChatHuggingFace(llm=endpoint)
```

Rules:

- Pin `provider="featherless-ai"`. Do not use `provider="auto"`.
- On 401, 403, empty body, or provider downtime, stop the generation cells and record the failure in the notebook outputs. Do not silently switch to Ollama, Gemini, build.nvidia, or another Llama checkpoint.
- Cap `max_new_tokens` (512 recommended) so answers stay short enough to compare with reference text.

### 5.5 Embedding construction (design contract)

```python
from langchain_huggingface import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
```

The same embedding function is reused for indexing, query embedding, answer similarity, and retrieval similarity.

### 5.6 Pre-download / warm-up (outside timed exercise)

Before a timed session, warm the MiniLM download and NLTK English stop words so offline steps do not block the exercise. The Hugging Face LLM call remains network-dependent.

---

## 6. Checkpoint design (100 marks)

### 6.1 Section 1 — Data loading, preparation, and analysis (40 marks)

#### 1.2.1 Load logistics documents (7 marks)

**Input:** `DATASET_DIR` as defined in Section 4.1.

**Behaviour:**

1. Recursively discover all `.md` and `.pdf` files under `dataset/`.
2. Load Markdown with a Markdown loader; load PDF with a PDF loader (`pypdf`).
3. Produce a list of LangChain `Document` objects with metadata:

| Metadata key | Source |
| --- | --- |
| `file_name` | Basename only (for example `OP-204_Incident_Management_v4.md`) |
| `category` | Immediate parent folder name (`operations`, `pdfs`, …) |
| `file_type` | `md` or `pdf` |
| `source_path` | Path relative to `DATASET_DIR` |

**Acceptance:**

- Exactly 10 documents.
- Every document has all four metadata keys.
- First-document inspection cell prints page content preview and metadata.

#### 1.2.2 Clean and normalise document text (5 marks)

**Behaviour:**

- Strip leading/trailing whitespace.
- Collapse consecutive spaces and blank lines without deleting headings, table pipes, currency amounts, document IDs, or critical notes.
- Preserve metadata unchanged.
- Do not paraphrase or summarise document meaning.

**Acceptance:**

- Cleaned corpus length equals 10.
- Spot-check that numbers such as `$10,000` and `2,800 psi` remain intact.

#### 1.3.1 Analyse document lengths (4 marks)

The brief does not name the length unit. **Primary metric is character count of cleaned `page_content`**, because chunk size is defined in characters. Also report word count (whitespace-split) beside character stats for readability.

Report for character lengths: minimum, maximum, and average across the 10 documents. Display a small table keyed by `file_name`.

#### 1.3.2 Analyse word frequencies (6 marks)

**Behaviour:**

1. Tokenise cleaned text (lowercase; keep alphabetic tokens of length ≥ 2, or an equivalent clear rule stated in the notebook).
2. Remove NLTK English stop words.
3. Report the 20 most frequent and 20 least frequent non-stop words across the corpus.
4. Break ties for least-frequent tokens alphabetically (many tokens occur once).

#### 1.3.3 Compare document similarity (6 marks)

**Behaviour:**

1. Fit a TF-IDF vectoriser on the 10 cleaned documents.
2. Compute pairwise cosine similarity.
3. Display a labelled 10×10 matrix (use `file_name` as labels).
4. In narrative output, call out the expected high similarity between the RGM Markdown and PDF copies.

#### 1.4.1 Create overlapping document chunks (12 marks)

**Parameters (fixed):**

| Parameter | Value |
| --- | --- |
| Chunk size | 800 characters |
| Chunk overlap | 120 characters |
| Metadata | Copied from parent document onto every chunk |

**Acceptance:**

- Function returns a list of chunk `Document`s.
- Total chunk count is printed.
- Sample chunk inspection shows text plus the four metadata keys.
- Chunk count is greater than document count.

---

### 6.2 Section 2 — Vector database and RAG chain (35 marks)

#### 2.1.1 Initialise the embedding model (5 marks)

Initialise `sentence-transformers/all-MiniLM-L6-v2` as specified in Section 5.5. Print the model name in the notebook so the submission states the embedding model clearly.

#### 2.1.2 Create and populate the vector database (11 marks)

**Collection:** `logistics_rag`

**Persistence:** Store under a local directory such as `../chroma/logistics_rag` (or a path next to the notebook). Do not commit this directory.

**Reproducibility rule (required by the brief):**

1. If a collection or persist directory already exists for this assignment run, delete it.
2. Recreate an empty collection.
3. Add all chunks once.

Re-running an append-only ingestion cell creates duplicate vectors and is treated as a defect.

**Acceptance:**

- Vector count equals chunk count.
- Retriever can return four documents for a smoke-test query.

#### 2.2.1 Build the RAG pipeline (12 marks)

Connect, in order:

1. Vector-store retriever with `search_kwargs={"k": 4}`.
2. Context formatter that joins retrieved chunk texts (include `file_name` in each block for transparency).
3. Grounded chat prompt (system + human) that:
   - Answers only from the supplied context.
   - States clearly when the context does not contain the answer.
   - Avoids inventing policies, budgets, or contacts.
   - When context sources conflict, reports the conflict instead of choosing silently.
4. Language model from Section 5.4.

Suggested system instructions (wording may vary):

```text
You are the AeroVelo Logistics Global operations assistant.
Answer using only the CONTEXT below.
If the CONTEXT does not contain enough information, say that the
supplied documents do not contain the answer.
Do not invent document IDs, amounts, roles, or procedures.
If CONTEXT passages disagree, state the disagreement and cite the
file names. Keep answers concise and factual.
```

Human template must include both `{context}` and `{question}`.

#### 2.2.2 Generate answers and display sources (7 marks)

Implement a function with signature conceptually:

```text
ask(question: str) -> dict with keys:
  answer: str
  sources: list[str]   # unique file_name values from the 4 retrieved chunks
  documents: list      # raw retrieved Documents (for evaluation)
```

Display:

1. Generated answer.
2. Retrieved source filenames.

**Smoke-test question (generation section, not one of the five graded pairs):**

> What safety override applies when a cycle-expired Valve-B unit continues to operate above 2,800 psi?

Expected grounding: BOM-FLT-H2NEX / OP-204 — continued operation constitutes a Tier-3 safety event under OP-204 regardless of calculated financial impact.

---

### 6.3 Section 3 — RAG evaluation (20 marks)

#### 3.1.1 Prepare evaluation questions and reference answers (4 marks)

Create five paired items. Reference answers are taken from the documents and must not be rewritten merely to improve similarity scores.

| ID | Theme | Question (use as written or with minor wording polish that preserves meaning) | Reference answer (ground-truth content) | Primary source |
| --- | --- | --- | --- | --- |
| Q1 | Supplier performance | What are the key performance indicator targets for Strategic and Preferred suppliers? | On-time delivery rate target >95%; quality acceptance rate target >99%; lead time adherence within ±5 days of quoted lead time; incident response time target <4 hours for critical supply disruptions. | AVL-PUR-012 |
| Q2 | Incidents | When does a Tier-2 logistics incident become a Critical Exception, and who must sign off? | If compounding costs, fines, or penalties of a single Tier-2 incident exceed $10,000 USD, the incident escalates to a Critical Exception. Critical Exceptions require formal written sign-off of the respective Regional Operations Vice President. | OP-204 §4.2 |
| Q3 | Regulatory reporting | What are the reporting windows and mandatory notification targets for Critical, Major, and Minor regulatory breaches? | Critical: 2 hours — Regional VP, General Counsel, relevant regulator. Major: 24 hours — Regional Operations Director, General Counsel. Minor: 72 hours — Regional Operations Director. | SOP-COM-015 Table 1 |
| Q4 | Supplier data processing | Does emergency procurement from EuroVolt GmbH require a provisional DPA? | EuroVolt GmbH has a Master DPA on file. Emergency procurement does not require a provisional DPA when (1) scope is within existing MDPA service categories, (2) no new personal data categories are introduced, and (3) the EMEA Regional Compliance Officer is notified within 24 hours. Otherwise the standard 72-hour provisional DPA rule applies. | LEG-GDPR-007 §5 |
| Q5 | Financial authorisation | Who must approve emergency procurement between $5,001 and $50,000, and what confirmation is required? | The Regional Operations Director must approve prior to commitment. Verbal approval is acceptable; written confirmation is required within 24 hours. | FIN-AUTH-101 Table 2 |

Store as a list of dicts: `question`, `reference_answer`, optional `id` / `theme`.

#### 3.1.2 Evaluate answer and retrieval similarity (10 marks)

Definitions from the brief:

| Metric | Definition |
| --- | --- |
| Answer similarity | Cosine similarity between MiniLM embeddings of the generated answer and the reference answer |
| Retrieval similarity | Highest cosine similarity between the MiniLM embedding of the reference answer and any of the four retrieved chunk texts |

Implementation outline:

1. For each of the five questions, call `ask(question)`.
2. Embed `generated_answer` and `reference_answer`; compute cosine similarity → answer score.
3. Embed each retrieved chunk; compute cosine with the reference answer; take the maximum → retrieval score.
4. Build a results table: question id, answer similarity, retrieval similarity, sources, short answer preview.
5. Compute mean answer similarity and mean retrieval similarity across the five supported questions only.

These scores are diagnostic measures. They are not accuracy percentages or proof of factual grounding.

#### 3.1.3 Interpret results and test unsupported questions (6 marks)

**Unsupported question (required):**

> What is the annual operating budget allocation for each regional division in AVL-BUD-2026?

Expected behaviour:

- The assistant states that the supplied documents do not contain the answer (AVL-BUD-2026 is cited but absent).
- Retrieved filenames are still displayed.
- Do not invent budget figures.

Interpretation narrative must cover:

- Average answer and retrieval similarity.
- At least one representative success and one weakness (for example, RGM Markdown/PDF duplicates consuming retrieval slots, or cross-document conflicts).
- Honest statement of model/runtime assumptions (Hugging Face Featherless, MiniLM, temperature 0).

---

### 6.4 Section 4 — Conclusion (5 marks)

#### 4.1.1 Summarise findings and limitations (5 marks)

Conclude with evidence from the notebook outputs:

1. Data analysis findings (length range, notable frequent terms, RGM Markdown–PDF similarity).
2. Chunking and vector-store observations (chunk count, vector count, refresh behaviour).
3. RAG pipeline behaviour on supported questions (sources returned, grounding quality).
4. Evaluation averages and unsupported-question behaviour.
5. Limitations of retrieval and evaluation (duplicate sources, corpus conflicts, diagnostic similarity scores, network dependency of the LLM endpoint).
6. One practical improvement (for example: diversify retrieval when RGM Markdown and PDF both hit; add citation of chunk ids; add a lightweight conflict flag when FIN-AUTH-101 and RGM-2026 both appear).

---

## 7. Starter notebook — modify in place

### 7.1 Implementation artifact

| Item | Value |
| --- | --- |
| File already present | [`practice-capstone-project/results/Logistics_Operations_RAG_Assistant_Starter.ipynb`](../results/Logistics_Operations_RAG_Assistant_Starter.ipynb) |
| Action | **Modify this notebook** — fill every empty code cell; keep markdown headings, mark tags, and narrative cells unless a factual correction is required (for example the Ollama install comment) |
| Do not | Start a blank notebook or relocate sections into a different file for day-to-day work |
| LMS export (optional rename) | When submitting, the brief suggests `Logisitic_Operation_RAG <group_name>.ipynb` (spelling as in the brief). Export or rename a completed copy for upload; keep the filled starter under `results/` in the repo |
| Title cell | Extend the first markdown cell (or add immediately under it) with the **group name** |
| Kernel | Project `.venv` (see Section 5.1) |

The notebook stays under `results/` so the repository’s `nbstripout` exclude retains visible outputs for review.

### 7.2 Starter structure map (every notebook ask)

The starter already contains Objective, Business Value, and section markdown. Preserve that prose. Implement code and conclusions against the empty `# …` cells as follows. Design details for each graded checkpoint are in Section 6.

| Starter section / placeholder | What the notebook asks | How this design covers it |
| --- | --- | --- |
| Title: Logistics Operations RAG Assistant | Assignment identity | Keep title; add group name near the start |
| Objective | Understand data; EDA; chunk; vector DB; retrieve; grounded LLM answers; evaluate retrieval, correctness, grounding, unsupported handling | Sections 1 and 6; do not delete the starter bullets |
| Business Value | Faster retrieval; operational support; consistent grounded answers; less manual search; unsupported queries | Section 1.2; leave starter text in place |
| **1.** Data Loading, Preparation and Analysis **[40]** | Parent section | Section 6.1 |
| **1.1** Data Understanding | Eight folders; Markdown + PDF; LangChain docs with source metadata | Section 4; loader metadata keys in §6.1 / 1.2.1 |
| **1.2** Load and Preprocess **[12]** | Parent section | 1.2.1 + 1.2.2 |
| Loading libraries / pip comments | Install useful packages | §5.1–5.2: use `.venv`; remove `langchain-ollama`; keep Hugging Face stack |
| `# Import essential libraries` | Imports | Import pandas, pathlib, nltk, sklearn, langchain loaders/splitters, HuggingFace embeddings/endpoint/chat, Chroma, etc. |
| **1.2.1** Load Logistics Documents **[7]** | Load all `.md` and `.pdf`; metadata: file name, business category, file type, source path | §6.1 / 1.2.1 — three cells: discover/load, attach metadata, inspect first document |
| **1.2.2** Clean and Normalise **[5]** | Remove unnecessary whitespace; preserve meaning and metadata | §6.1 / 1.2.2 |
| **1.3** Exploratory Data Analysis **[16]** | Parent section | 1.3.1–1.3.3 |
| **1.3.1** Analyse Document Lengths **[4]** | Average, maximum, minimum document length | §6.1 / 1.3.1 — characters primary; word count optional beside it |
| **1.3.2** Analyse Word Frequencies **[6]** | Most and least frequently occurring words | §6.1 / 1.3.2 — top/bottom 20 non-stop words (brief); NLTK English stop words |
| **1.3.3** Compare Document Similarity **[6]** | TF-IDF vectors and cosine similarity | §6.1 / 1.3.3 — labelled 10×10 matrix |
| **1.4** Document Creation and Chunking **[12]** | Parent section | 1.4.1 |
| **1.4.1** Create Overlapping Chunks **[12]** | Split into overlapping chunks; preserve metadata | §6.1 / 1.4.1 — size 800, overlap 120; cells: define function, process all, count, inspect sample |
| **2.** Vector Database and RAG Chain **[35]** | Parent section | Section 6.2 |
| **2.1** Vector Embeddings and Database **[16]** | Parent section | 2.1.1 + 2.1.2 |
| **2.1.1** Initialise Embedding Model **[5]** | Embedding function for chunks | §6.2 / 2.1.1 — `all-MiniLM-L6-v2` |
| **2.1.2** Create and Populate Vector Database **[11]** | Load chunk embeddings into Chroma | §6.2 / 2.1.2 — collection `logistics_rag`; delete-and-recreate; function to add chunks; count vectors |
| **2.2** Create the RAG Chain **[19]** | Parent section | 2.2.1 + 2.2.2 |
| **2.2.1** Build the RAG Pipeline **[12]** | Connect retriever, prompt, and language model | §6.2 / 2.2.1 — cells: format context, create chain, initialise chain; LLM = Llama 3.2 3B Instruct via Featherless (§5.4), not Ollama |
| **2.2.2** Generate Answers and Display Sources **[7]** | QA function; answer + source documents | §6.2 / 2.2.2 — `ask()`; test with Valve-B / 2,800 psi smoke question; show filenames |
| **3.** RAG Evaluation **[20]** | Parent section | Section 6.3 |
| **3.1** Evaluation and Inference **[20]** | Parent section | 3.1.1–3.1.3 |
| **3.1.1** Prepare Evaluation Questions **[4]** | Small set of logistics questions and ground-truth answers | §6.3 / 3.1.1 — five fixed pairs (supplier KPIs, Critical Exception, breach windows, EuroVolt DPA, emergency procurement $5,001–$50,000) |
| **3.1.2** Evaluate Answer and Retrieval Similarity **[10]** | Function to evaluate; semantic similarity of answer vs ground truth and relevance of retrieved context | §6.3 / 3.1.2 — MiniLM cosine answer similarity + max chunk–reference retrieval similarity; per-question table + averages |
| **3.1.3** Interpret Results and Unsupported Questions **[6]** | Infer from scores; test unsupported question; summarise averages; verify no unsupported invention | §6.3 / 3.1.3 — AVL-BUD-2026 unsupported question; narrative interpretation |
| **4.** Conclusion **[5]** | Parent section | Section 6.4 |
| **4.1** Conclusions and Insights **[5]** | Parent section | 4.1.1 |
| **4.1.1** Summarise Findings and Limitations **[5]** | Conclude from data analysis, chunking, vector retrieval, RAG pipeline, and evaluation | §6.4 / 4.1.1 — fill the two empty conclusion cells with written findings, limitations, and one practical improvement |

### 7.3 Required visible outputs

After a full run of the starter notebook, these outputs must be visible in the cells:

- Document load count (10) and first-document inspection.
- Cleaning confirmation (and sample if useful).
- Length statistics (min / max / average).
- Most and least frequent non-stop words (20 each).
- TF-IDF cosine similarity matrix.
- Chunk total and sample chunk (with metadata).
- Embedding model name.
- Chroma vector count (equal to chunk count).
- Smoke-test answer with retrieved source filenames.
- Evaluation table, per-question scores, and averages for the five supported questions.
- Unsupported-question answer that refuses to invent missing budget data, plus sources.
- Written conclusions covering analysis, chunking, retrieval, RAG, evaluation, limitations, and one improvement.

### 7.4 What not to submit / commit

- Full dataset embedded in cells.
- Hugging Face tokens or any private credentials.
- The `.venv/` virtual environment directory.
- Chroma persist directories committed to git.
- Altered reference answers chosen only to raise similarity scores.
- A second “shadow” notebook that diverges from the starter structure for the graded submission.

### 7.5 Assumptions to state in the notebook

Record near the RAG setup or conclusion cells:

- Runtime: packages installed in project `.venv`; notebook kernel bound to that environment.
- Implementation file: this starter notebook under `practice-capstone-project/results/`.
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`.
- Language model: `meta-llama/Llama-3.2-3B-Instruct` via Hugging Face Inference Provider `featherless-ai` (not Ollama / Gemini / build.nvidia).
- Temperature / sampling: `do_sample=False`, temperature 0.
- Dataset path: `../dataset` relative to the notebook.
- Chroma collection name `logistics_rag` and that the collection is deleted and recreated before indexing.
- Network requirement for LLM calls; local availability of MiniLM and NLTK data.

---

## 8. Suggested build order

Work **inside** [`Logistics_Operations_RAG_Assistant_Starter.ipynb`](../results/Logistics_Operations_RAG_Assistant_Starter.ipynb). Matches the brief’s 2–2.5 hour schedule; use for team division of labour.

| Phase | Focus | Starter checkpoints to fill |
| --- | --- | --- |
| 0 | Activate `.venv`, fix pip cell (drop Ollama), set kernel, confirm `../dataset` | Loading libraries / imports |
| A | Load, inspect, clean | 1.2.1, 1.2.2 |
| B | Lengths, frequencies, TF-IDF | 1.3.1–1.3.3 |
| C | Chunks, embeddings, Chroma | 1.4.1, 2.1.1, 2.1.2 |
| D | RAG chain and source display | 2.2.1, 2.2.2 |
| E | Five supported + one unsupported evaluation | 3.1.1–3.1.3 |
| F | Conclusions, assumptions, reproducibility check | 4.1.1 |

---

## 9. Acceptance checklist (pre-submission)

- [ ] Work was done by modifying `practice-capstone-project/results/Logistics_Operations_RAG_Assistant_Starter.ipynb` (starter structure retained)
- [ ] Group name and assignment title at the top of the notebook
- [ ] Starter Objective / Business Value / 1.1 markdown retained
- [ ] Pip cell no longer installs `langchain-ollama`
- [ ] Exactly 10 documents loaded with `file_name`, `category`, `file_type`, `source_path`
- [ ] Whitespace cleaned; meaning preserved
- [ ] Min / max / average document lengths reported (characters primary)
- [ ] 20 most and 20 least frequent non-stop words reported
- [ ] TF-IDF cosine similarity matrix displayed
- [ ] Chunks: size 800, overlap 120, metadata preserved; count + sample shown
- [ ] Embeddings: `all-MiniLM-L6-v2`
- [ ] Chroma collection `logistics_rag` populated after delete-and-recreate; vector count shown
- [ ] Retriever `k=4`; grounded prompt; Llama 3.2 3B Instruct via Featherless; temperature 0
- [ ] QA function returns answer and displays retrieved filenames (smoke test run)
- [ ] Five evaluation pairs unchanged in substance; evaluation function run; averages reported
- [ ] Unsupported AVL-BUD-2026 question refuses to invent figures
- [ ] Conclusions cite observed outputs and one improvement (empty conclusion cells filled)
- [ ] Notebook kernel uses the project `.venv`
- [ ] No secrets, no embedded dataset, no committed `.venv/` or Chroma store

---

## 10. Out of scope

- Live system integrations (GIR, procurement systems, email, hotlines).
- Fine-tuning or changing the embedding model.
- Rerankers, multi-query retrieval, or agent tool calling (optional future work only).
- Resolving FIN-AUTH-101 vs RGM-2026 conflicts inside the generator by inventing policy.
- Using build.nvidia, Ollama, or Gemini in the graded notebook.

---

## 11. References

1. Assignment brief: `dumps/practice-capstone-project/RAG Assignment-Logistics Operations Assistant.pdf`
2. Starter notebook to modify in place: `practice-capstone-project/results/Logistics_Operations_RAG_Assistant_Starter.ipynb`
3. Dataset: `practice-capstone-project/dataset/`
4. Hugging Face model card: `https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct`
5. LangChain Hugging Face chat integration: `langchain-huggingface` (`HuggingFaceEndpoint`, `ChatHuggingFace`)
6. Embedding model: `https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2`
