# Dev-set runs and the prompt freeze (plan step 10)

Tuned on the **20 dev scenarios (23 turns) only**. The frozen eval set (`eval-v1`) and the corrections suite were not run or looked at. Every run: planner mode, one request at a time, scored with `eval/score.py` (SPEC §10). Per-run reports are in `runs/dev-0N/summary.md`, raw cards in `runs/dev-0N/raw.jsonl`, and calls in `docs/quota-log.md`.

Before the first live run, an **oracle run** (`eval/oracle_dev.py`) gave the pipeline perfect model replies and scored **23/23**. So every failure below is the model's, and each fix targets a model behaviour.

| Run | Turns correct | Amount right (answered) | Citation claims | Clarify (recall / precision) | Facts invented | Router fallbacks | Escalations | Chat / embed calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|
| dev-01 | 14/23 (61%) | 10/17 | 43/45 | 1/3, 1/1 | 9 | 12 | 2 | 87 / 17 | 73,773 |
| dev-02 | 19/23 (83%) | 15/17 | 43/45 | 2/3, 2/3 | 2 | 3 | 3 | 84 / 18 | 74,828 |
| dev-03 | 16/23 (70%) | 12/17 | 31/45 | 3/3, 3/3 | 0 | 1 | 0 | 63 / 13 | 57,464 |
| dev-04 | 22/23 (96%) | 17/17 | 45/45 | 3/3, 3/3 | 1 | 0 | 0 | 77 / 17 | 70,946 |
| **dev-05** (v1) | **23/23 (100%)** | **17/17** | **45/45** | **3/3, 3/3** | 1 | 0 | 0 | 68 / 17 | 64,742 |
| dev-06 (v2) | 23/23 | 17/17 | 45/45 | 3/3, 3/3 | 1 | 0 | 0 | 72 / 17 | 74,509 |
| dev-07 (v3) | 23/23 | 17/17 | 45/45 | 3/3, 3/3 | 1 | 0 | 0 | 71 / 17 | 73,100 |
| dev-08 (v4) | 23/23 | 17/17 | 45/45 | 3/3, 3/3 | 1 | 0 | 0 | 71 / 17 | 73,123 |

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

## Live smoke tests and freezes v2–v3 (18 Nov)

The UI's example questions (written for the UI, not eval items) were run through the Docker stack, the path the browser uses. Results: `runs/smoke-01.json`, `runs/smoke-02.json`; calls in `docs/quota-log.md`.

**Smoke 1 (agent v1): 2 of 6 turns wrong.** Neither failure type is scored by the dev set:
- **Tijuana day trip: $3.34 owed instead of nothing.** Two causes. The intake gave no arrival country. And `tools/facts.py` did not ask about it, even though the signed-off facts table makes "trip length or arrived from Mexico" one fact: a trip under 48 hours still gets $800 when it comes straight from Mexico (R9).
- **A false sentence in the working.** "You used it within the last 30 days" was written for a traveller who hadn't. The writer saw only figures and sources (one was the 30-day rule), not the traveller's facts. The deterministic verifier checks numbers and handles, not meaning.

**Freeze v2** (confirmed by dev-06, 23/23):
- **Missing fact:** `facts.py` treats the trip fact as missing when the trip is under 48 hours and the arrival country is unknown, unless the countries named rule Mexico out.
- **Intake prompt:** a city or region means its country.
- **Writer:** it gets the traveller's facts ("the only things you may say about them"), and each source carries the rule it supports.
- **Verifier:** a sentence saying the exemption the calculators gave "doesn't apply / doesn't qualify" is a wording failure. It caught the same hallucination on dev DV12 and DV13, which the dev score never saw, and the rewrite fixed both.
- **Display:** stick counts no longer repeat the item ("200 cigarettes of cigarettes").

**Smoke 2 (agent v2):** every answer was right and the false sentence was gone. Tijuana was now asked about instead of answered wrongly. But with "Tijuana, Mexico, driving straight back", the intake still put Mexico only in `countries_visited`, so the agent asked again.

**Freeze v3** (confirmed by dev-07, 23/23):
- **Grounding:** a one-country trip comes back from that country.
- **Live check:** the Tijuana question then answered "$800 exemption, nothing owed", which is correct.

`pack/agent.lock.yaml` is now version 3.

## Freeze v4: hardening (step 12)

The findings came from the safety suite and the red-team (`safety.md`, `red-team.md`), not from eval items. Confirmed by dev-08 (23/23), the red-team re-run (22/22) and the safety probes (all agent-mode probes pass).

- **Guard:**
  - look-alike characters are read as letters ("h1de");
  - Spanish evasion words are refused;
  - "without the officer noticing" is refused;
  - "hide nothing" is allowed.

  Before the fix, the three evasions got a clarify question instead of a refusal.
- **Banned patterns:** negated declaring ("do not need to be declared"), "abolished" and "never checks" are banned, and so is a guarantee unless it's negated ("we can't guarantee" is fine). These are the planted claims the literal phrases missed.
- **Scope flags:** the traveller's quote must contain words that say crew, non-resident or shipped. "I'm a CBP supervisor" had been accepted as evidence for crew, so a wine question got the crew scope note.
- **Verifier routing:** after the one rewrite, working sentences whose only fault is a missing source are dropped instead of escalating a correct answer. A nothing-owed answer had escalated for "There is no volume over the allowance [F4]."

## Freeze v5: tobacco over the allowance is never taxed (20 Nov)

- **Found:** a live answer for the Dubai cigarettes (demo script, question 3) said the over-limit cigarettes "may be subject to duty and excise". R5 says tobacco over the allowance is not taxed (`tobacco_excess_outcome: seizure_risk`), and the card's bottom line and notes already said "seized". The verifier checked only the bottom line, so the wrong working sentence passed.
- **Changed:** `verifier.py` flags any working sentence that puts duty, excise or tax on tobacco without a negation or "duty-free" (`tobacco_taxed_sentences`). `graph.py` `drop_unsourced` drops those sentences, as it already drops unsourced ones, and nothing else changes. The bottom line, notes and sources are unchanged.
- **Checked:** `tests/test_tobacco_wording.py` (4 offline tests). The full offline suite is run with this freeze. **Not yet checked:** a dev-set rerun and a live question; both need the user's OK because they call the endpoint.

## Freeze v6: option A reranker shipped (20 Nov)

- **Change:** the search reranks the fused top 10 with Qwen3-8B (listwise) and cuts each passage to 120 tokens (`RERANKER=listwise`, `RERANKER_POOL=10`, `RERANKER_PASSAGE_TOKENS=120`). It is the reranker the Track B brief requires. Each rerank call counts toward the question's model-call and token caps.
- **Measured before the freeze:** docs/results/retrieval/rerank_a.json. Recall@1 rises (dev 0.22 -> 0.40, frozen 0.24 -> 0.38). Recall within the 1,500-token budget falls (dev 0.84 -> 0.80, frozen 0.77 -> 0.75). Hard negatives in the top 5 rise (dev 4% -> 9%, frozen 6% -> 11%). No fallbacks or errors. About 1,340 tokens per call, so a typical turn stays under the 12,000-token cap.
- **Checked:** offline tests (`tests/test_reranker_shipped.py`). **Not yet checked:** a dev agent run and the official reruns. Both need the user's OK and the endpoint.

## After freeze v6: dev-09 and the official reruns (20–21 Nov)

- **Dev run dev-09** (agent v6, 23 turns): 22 of 23 turns right. DV13 (mixed basket) was cut off by the cap at 12,772 tokens, against 12,000. It was run and kept as is.
- **Official reruns** (agent v6, 91 turns): planner 71 of 91 turns right in all three runs; corrections 12 of 12 in all three; router 72 of 91; tool-calling and plain RAG unchanged from v4. Three turns hit the cap that answered under v4: planner B04 (12,678 tokens) and F04 (12,424), and router B04 (12,043). The reranker's calls (about 1,340 tokens each) count against the same per-question cap, so the cap now binds on a few longer turns.
- **Not decided:** whether to raise the cap (a new freeze and full reruns) or keep the cap and report these turns as cap escalations. The report currently says the second. The B04 and F04 labels in `hand-check.yaml` are drafted and await review.
