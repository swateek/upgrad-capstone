# Brief: paraphrase set (generalisation check)

**For whoever writes the questions: you, or a Claude session that has NOT worked on this agent's code.**
The session that built the agent knows which patterns the code looks for, so its paraphrases would
avoid the gaps. Do not open `src/` (the guard, intake and router code). Read only this brief,
`eval/dev_set.jsonl` and, if useful, `docs/SPEC.md`.

## Why

The agent scores 20/20 on the dev set, but every dev failure was fixed by hand, so dev is no longer an
honest test. This set asks: does it still work when the same situations are worded differently?
Each new question keeps **exactly the facts** of one dev question, so it keeps that question's gold
answer, and no new gold has to be calculated.

## What to write

For each of the 20 dev questions (D01-D20), write **3 rewordings**: 60 questions in total. Each one must
describe the same traveller, the same items and the same request, so the correct answer is identical.

Vary as many of these as feel natural, a different mix each time:

- wording, tone and order of facts (casual, terse, rambling, formal; question first or last);
- how a fact is expressed, keeping its value: "10 days" / "a week and a half" is NOT allowed (10.5 days
  is a different fact), but "10 days" / "ten days" / "10-day trip" is fine; "$30 each" / "30 dollars a
  bottle" / "paid $30 per bottle"; "13%" / "13% ABV" / "13 percent alcohol";
- units with the same value: "750 ml" / "75 cl" / "a standard 750 ml bottle"; "1-litre" / "1 L" / "a litre";
  "a carton (200)" / "a carton of 200";
- places with the same meaning: a city instead of the country, or the country instead of a city, as
  long as it is unambiguous (Kraków / Poland; Tijuana / Mexico on a day trip) and the arrival route stays the same;
- "made in X" / "X-made" / "an X brand" instead of "X wine";
- irrelevant extra detail (why they travelled, who they were with), typos, lower case, no punctuation;
- for refusals (D16-D19): new wording of the same intent: other ways to ask about nicotine pouches,
  other crew roles described the same way, other ways to ask how to get bottles past customs unseen,
  other ways to slip an instruction into the question.

**Never change:** any number (count, size, ABV, price, age, trip length), any country, whether the
exemption was used recently, where they arrive, what they ask (owe? allowed? how many?), and, for
D13 and D14, which facts are **missing**: a rewording must not add the age, trip length or 30-day
history that the original leaves out (and must not drop a fact the original gives).

D20: copy its `inject_into_retrieval` block unchanged; only the question is reworded.

## Format

One JSON object per line in `eval/paraphrase_raw.jsonl`:

```json
{"id": "P01a", "source": "D01", "question": "Just back from Italy, 10 days. Got four 750 ml bottles of wine (13%), paid $30 a bottle. I'm 34, haven't used my duty-free allowance lately. Do I owe?", "changed": "order, wording"}
```

- `id`: `P` + dev number + `a`/`b`/`c`.
- `source`: the dev id whose facts it keeps.
- `changed`: a few words on what you varied.
- Do **not** write gold answers: `eval/build_paraphrase.py` copies each item's gold from its source.

Then run `uv run python eval/build_paraphrase.py`, which checks the file and writes `eval/paraphrase_set.jsonl`.

## Rules for using the result

- It is a **one-shot check**, run once with the agent as it is. If we fix things and re-run it until it
  passes, it becomes a second dev set and stops measuring anything.
- Failures are read for **kinds** of weakness (for example: "spelled-out numbers", "city names"), and any
  fix must be general. Each fix is logged in `docs/COMPENSATIONS.md` with the before number from this run.
- Never use `eval/eval_set.jsonl` for this (CLAUDE.md rule 6).
