# Dev-set runs and the prompt freeze (plan step 10)

Tuned on the **20 dev scenarios (23 turns) only**. The frozen eval set (`eval-v1`) and the corrections suite were not run or looked at. Every run: planner mode, one request at a time, scored with `eval/score.py` (SPEC §10). Per-run reports are in `runs/dev-0N/summary.md`, raw cards in `runs/dev-0N/raw.jsonl`, and calls in `docs/quota-log.md`.

Before the first live run, an **oracle run** (`eval/oracle_dev.py`) gave the pipeline perfect model replies and scored **23/23**. So every failure below is the model's, and each fix targets a model behaviour.

| Run | Turns correct | Amount right (answered) | Citation claims | Clarify (recall / precision) | Facts invented | Router fallbacks | Escalations | Chat / embed calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|
| dev-01 | 14/23 (61%) | 10/17 | 43/45 | 1/3, 1/1 | 9 | 12 | 2 | 87 / 17 | 73,773 |
| dev-02 | 19/23 (83%) | 15/17 | 43/45 | 2/3, 2/3 | 2 | 3 | 3 | 84 / 18 | 74,828 |
| dev-03 | 16/23 (70%) | 12/17 | 31/45 | 3/3, 3/3 | 0 | 1 | 0 | 63 / 13 | 57,464 |
| dev-04 | 22/23 (96%) | 17/17 | 45/45 | 3/3, 3/3 | 1 | 0 | 0 | 77 / 17 | 70,946 |
| **dev-05** | **23/23 (100%)** | **17/17** | **45/45** | **3/3, 3/3** | 1 | 0 | 0 | 68 / 17 | 64,742 |

dev-05 per turn: 3.0 model calls on average (max 5), 3.6 tool calls, 2,815 tokens (max 5,508 of the 12,000 budget); latency p50 14.8 s, p95 33.4 s on the shared endpoint.

## What each run changed

**After dev-01** (14/23):
- **Intake: trip length as a number only.** The schema let `trip_hours` be `"<48"` or `">=48"`, and the model chose `"<48"` for 6-, 8- and 10-day trips, causing 5 wrong amounts. Now `trip_hours` is a number, and a separate yes/no is used only when no length is given (`IntakeProfile`).
- **Scope flags need the traveller's words.** "Back from a week in Dublin" was read as non-resident. Now `us_resident`, `crew` and `shipped` need a `scope_quote` that is in the conversation, or code drops the flag.
- **Prompt: never take the origin from a brand**, and never fill a value, state or origin that wasn't given.
- **Writer:** with no figures, use no [F] handles.
- **Plan repair.** The model attached `lines` to steps that take none, and added the state lookup with no state, in most plans (12 router fallbacks). The validator now drops these harmless extras (`plan_repaired`). Missing, repeated or misordered steps are still rejected.

**After dev-02** (19/23):
- **Grounding in code.** The intake still read "Havana Club" as made in Cuba and dropped the brand, and gave "ON" as an arrival state. Now:
  - an ambiguous brand the traveller names (from the signed-off R12 list) is recorded on its line;
  - a Cuban origin is kept only if the traveller mentions Cuba, so the agent asks once (Decision E);
  - an arrival state must be a US code.
- **Prohibited-only answers use a code template.** There are no figures to word, and the writer kept inventing `[F1]` and copying years from the OFAC text.
- Intake prompt: list non-alcohol goods too (DV18). **This caused the dev-03 regression.**

**After dev-03** (16/23, a regression):
- **Reverted:** the DV18 line made the model label wine and spirits as `other` (4 turns). It's replaced by narrower wording in the `item` field.
- **Grounding:** cigar vs cigarette must match the traveller's words ("10 cigars" came back as cigarettes). An ml quantity smaller than one container counts containers ("a 50 ml bottle" came back as 1 ml).
- **Prompt:** a clarify reply fills in the existing line.
- **Plan repair:** drop the calculators when no line is allowed in.

**After dev-04** (22/23):
- **Merge clarify replies.** "It says Puerto Rico on the label" still came back as a second bottle. On a reply to a facts-only question, a new line that repeats an existing one is merged into it (`reply_line_merged`).
- **Plan repair:** append a missing `search_regulations`. It always runs last, in code.

## Freeze

**Agent freeze v1** (`pack/agent.lock.yaml`, from dev-05) locks 27 files by sha256:
- the agent prompts;
- the guard policy;
- `customs/agent/*`;
- search and query building;
- the calculators and tools.

`tests/test_agent_freeze.py` fails, naming the file, if any of them changes. A change after the freeze needs a version bump and a reason written here.

Known limits carried into the official runs:
- `whatif_optimise` (stretch) is not built, so the 4 `whatif` items will fail. Building it needs freeze v2.
- Dev covers 20 scenarios. Several fixes target behaviours seen once or twice (DV07, DV09, DV11), so the frozen set will show how far they generalise.
- The intake still invents a price now and then (1 field in dev-05). It changes no dev answer, because those lines are within the allowance.
