"""Week-1 baselines (plan step 8, Track B item II): the bare model, single prompts, no tools, no
calculators, no retrieval. Run on the FROZEN eval-v1 set (measurement only; nothing is tuned).

    uv run python -m eval.baseline --dry-run            # exact call count; sends nothing
    uv run python -m eval.baseline --who swateek        # calls the upgrad CHAT endpoint (needs OK)
    uv run python -m eval.baseline --report-only        # rebuild the CSVs from raw results

Strategies (each plays the scenario's turns as a conversation):
    closed_book   zero-shot, prompted JSON                               1 call per turn
    fewshot_json  3 dev examples, strict json_schema                     1 call per turn
    cot_sc        chain of thought, 3 samples at T=0.7, majority vote    3 calls per turn
    decompose     facts -> working -> answer                             3 calls per turn
plus the intake comparison: fact extraction with vs without constrained decoding (2 per scenario).

Raw results are appended per item to docs/results/baselines/raw.jsonl, so an interrupted run
resumes. Outputs: docs/results/week1_strategies.csv, week1_failures.csv, week1-baselines.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Literal

import openai
from pydantic import BaseModel, ConfigDict

from customs.config import PROJECT_ROOT, get_settings
from customs.ingest.index import append_quota_log
from customs.llm.budget import TokenBudgetExceeded
from customs.llm.chat import ChatClient, MalformedOutput
from customs.observability.tracing import Tracer
from customs.tools.facts import QUESTIONS
from customs.tools.models import Line, Profile
from eval.score import load_corpus, score_extraction, score_turn

EVAL = PROJECT_ROOT / "pack" / "eval"
PROMPTS = PROJECT_ROOT / "pack" / "prompts"
OUT = PROJECT_ROOT / "docs" / "results"
RAW = OUT / "baselines" / "raw.jsonl"
STRATEGIES = {"closed_book": 1, "fewshot_json": 1, "cot_sc": 3, "decompose": 3}
INTAKE_MODES = ("intake_constrained", "intake_prompted")
COT_SAMPLES = 3

Outcome = Literal["answered", "clarify", "refused", "out_of_scope", "escalated"]
Kind = Literal[
    "owe", "nothing_owed", "prohibited", "seizure_risk", "mixed",
    "clarify", "refused", "out_of_scope", "escalated",
]  # fmt: skip


class Answer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    outcome: Outcome
    kind: Kind
    owe_usd: float | None
    clarify_question: str | None
    citations: list[str]
    answer: str


class CotAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    reasoning: str
    outcome: Outcome
    kind: Kind
    owe_usd: float | None
    clarify_question: str | None
    citations: list[str]
    answer: str


class Intake(BaseModel):
    model_config = ConfigDict(extra="ignore")
    profile: Profile
    basket: list[Line]


class Work(BaseModel):
    model_config = ConfigDict(extra="ignore")
    missing_fact: str | None
    exemption_usd: float | None
    prohibited: list[str]
    over_allowance: list[dict]
    total_owed_usd: float | None
    rules: list[str]


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip()


def load_rows(name: str) -> list[dict]:
    return [json.loads(x) for x in (EVAL / name).read_text(encoding="utf-8").splitlines() if x]


# --- few-shot examples: DEV set only ---------------------------------------------------------------

FEWSHOT_IDS = [("DV01", 0), ("DV10", 0), ("DV15", 0)]


def fewshot_messages() -> list[dict]:
    corpus = load_corpus()
    dev = {r["id"]: r for r in load_rows("dev.jsonl")}
    msgs = []
    for sid, turn in FEWSHOT_IDS:
        row, g = dev[sid], dev[sid]["gold"][turn]
        cites = [corpus.by_id[c["acceptable"][0]] for c in g.get("citations", [])]
        clar = " ".join(QUESTIONS[f] for f in g.get("clarify_fields", [])) or None
        ans = {
            "outcome": g["outcome"],
            "kind": g["bottom_line"]["kind"],
            "owe_usd": float(g["bottom_line"]["owe_usd"])
            if g["bottom_line"].get("owe_usd")
            else None,
            "clarify_question": clar,
            "citations": cites,
            "answer": clar or g["bottom_line"]["text"],
        }
        msgs += [
            {"role": "user", "content": row["turns"][turn]},
            {"role": "assistant", "content": json.dumps(ans)},
        ]
    return msgs


# --- strategies --------------------------------------------------------------------------------------


def _pred(a: BaseModel | None) -> dict:
    if a is None:
        return {}
    d = a.model_dump()
    return {
        k: d.get(k)
        for k in ("outcome", "kind", "owe_usd", "citations", "clarify_question", "answer")
    }


class Runner:
    def __init__(self, chat: ChatClient) -> None:
        self.chat = chat
        self.system = prompt("baseline_system")
        self.fewshot = fewshot_messages()

    def _call(self, messages, model, max_tokens, constrained=True, temperature=0.0, name="chat"):
        try:
            r = self.chat.complete(
                messages, max_tokens=max_tokens, response_model=model,
                constrained=constrained, temperature=temperature, name=name,
            )  # fmt: skip
            return r.parsed, r, None
        except MalformedOutput as err:
            return None, err.result, "invalid_json"
        except TokenBudgetExceeded as err:
            return None, None, f"budget:{err}"
        except (openai.APIStatusError, openai.APIConnectionError) as err:
            code = getattr(err, "status_code", "connection")
            return None, None, f"api_error:{code}"

    def turn(self, strategy: str, history: list[dict]) -> tuple[dict, dict]:
        """history: alternating user/assistant messages ending with the user's turn."""
        stats = {"calls": 0, "tokens": 0, "seconds": 0.0, "first_try_valid": True, "error": None}

        def acc(res, err):
            if res is not None:
                stats["calls"] += res.calls
                stats["tokens"] += res.total_tokens
                stats["seconds"] += res.seconds
                stats["first_try_valid"] &= res.calls == 1
            if err:
                stats["error"] = err

        sys_msg = [{"role": "system", "content": self.system}]
        if strategy == "closed_book":
            a, res, err = self._call(
                sys_msg + history, Answer, 500, constrained=False, name="closed_book"
            )
            acc(res, err)
            return _pred(a), stats
        if strategy == "fewshot_json":
            a, res, err = self._call(
                sys_msg + self.fewshot + history, Answer, 500, name="fewshot_json"
            )
            acc(res, err)
            return _pred(a), stats
        if strategy == "cot_sc":
            sys_cot = [{"role": "system", "content": self.system + "\n\n" + prompt("baseline_cot")}]
            samples = []
            for k in range(COT_SAMPLES):
                a, res, err = self._call(
                    sys_cot + history, CotAnswer, 900, temperature=0.7, name=f"cot_{k}"
                )
                acc(res, err)
                if a is not None:
                    samples.append(a)
            if not samples:
                return {}, stats
            votes = Counter(
                (s.outcome, None if s.owe_usd is None else round(s.owe_usd, 2)) for s in samples
            )
            best = votes.most_common(1)[0][0]
            chosen = next(
                s for s in samples
                if (s.outcome, None if s.owe_usd is None else round(s.owe_usd, 2)) == best
            )  # fmt: skip
            return _pred(chosen), stats
        if strategy == "decompose":
            convo = "\n".join(f"{m['role']}: {m['content']}" for m in history)
            facts, res, err = self._call(
                [{"role": "system", "content": prompt("baseline_decompose_facts")},
                 {"role": "user", "content": convo}],
                Intake, 600, name="decompose_facts",
            )  # fmt: skip
            acc(res, err)
            facts_json = facts.model_dump_json(exclude_none=True) if facts else "{}"
            work, res, err = self._call(
                [{"role": "system", "content": self.system + "\n\n" + prompt("baseline_decompose_work")},
                 {"role": "user", "content": f"Conversation:\n{convo}\n\nFacts:\n{facts_json}"}],
                Work, 700, name="decompose_work",
            )  # fmt: skip
            acc(res, err)
            work_json = work.model_dump_json() if work else "{}"
            a, res, err = self._call(
                [{"role": "system", "content": self.system + "\n\n" + prompt("baseline_decompose_answer")},
                 {"role": "user", "content": f"Conversation:\n{convo}\n\nFacts:\n{facts_json}\n\nWorking:\n{work_json}"}],
                Answer, 500, name="decompose_answer",
            )  # fmt: skip
            acc(res, err)
            return _pred(a), stats
        raise ValueError(strategy)

    def intake(self, mode: str, turns: list[str]) -> tuple[dict, dict]:
        msgs = [
            {"role": "system", "content": prompt("intake")},
            {"role": "user", "content": "\n".join(f"Traveller: {t}" for t in turns)},
        ]
        a, res, err = self._call(
            msgs, Intake, 600, constrained=(mode == "intake_constrained"), name=mode
        )
        stats = {
            "calls": res.calls if res else 0,
            "tokens": res.total_tokens if res else 0,
            "seconds": res.seconds if res else 0.0,
            "first_try_valid": bool(res) and res.calls == 1 and err is None,
            "error": err,
        }
        return (a.model_dump(exclude_none=True) if a else {}), stats


# --- run ------------------------------------------------------------------------------------------------


def done_keys() -> set[tuple]:
    if not RAW.exists():
        return set()
    return {(r["id"], r["strategy"]) for r in map(json.loads, RAW.read_text().splitlines()) if r}


def count_calls(rows: list[dict]) -> int:
    turns = sum(len(r["turns"]) for r in rows)
    return turns * sum(STRATEGIES.values()) + len(rows) * len(INTAKE_MODES)


def run(who: str, rows: list[dict], runner: Runner, tracer: Tracer) -> tuple[int, int]:
    RAW.parent.mkdir(parents=True, exist_ok=True)
    done = done_keys()
    corpus = load_corpus()
    total_calls = total_tokens = 0
    with RAW.open("a", encoding="utf-8") as fh:
        for row in rows:
            for strategy in [*STRATEGIES, *INTAKE_MODES]:
                if (row["id"], strategy) in done:
                    continue
                tags = ["baseline", "eval-v1", strategy, row["category"], row["id"]]
                with tracer.run(
                    f"baseline-{row['id']}-{strategy}",
                    row["turns"][0],
                    tags,
                    name="customs-baseline",
                ):
                    if strategy in INTAKE_MODES:
                        pred, stats = runner.intake(strategy, row["turns"])
                        rec = {"id": row["id"], "strategy": strategy, "category": row["category"],
                               "pred": pred, "stats": stats,
                               "extraction": score_extraction(pred, row["facts"])}  # fmt: skip
                        total_calls += stats["calls"]
                        total_tokens += stats["tokens"]
                    else:
                        history, turns_out = [], []
                        for i, text in enumerate(row["turns"]):
                            history.append({"role": "user", "content": text})
                            pred, stats = runner.turn(strategy, history)
                            s = score_turn(pred, row["gold"][i], corpus)
                            turns_out.append({"turn": i + 1, "pred": pred, "stats": stats,
                                              "correct": s.correct, "score": s.__dict__})  # fmt: skip
                            total_calls += stats["calls"]
                            total_tokens += stats["tokens"]
                            history.append(
                                {"role": "assistant", "content": pred.get("answer") or "(no reply)"}
                            )
                        rec = {
                            "id": row["id"],
                            "strategy": strategy,
                            "category": row["category"],
                            "turns": turns_out,
                        }
                fh.write(json.dumps(rec, default=str) + "\n")
                fh.flush()
            print(f"done {row['id']}", flush=True)
    tracer.flush()
    return total_calls, total_tokens


# --- report ---------------------------------------------------------------------------------------------


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}" if b else "n/a"


def report() -> None:
    recs = [json.loads(x) for x in RAW.read_text().splitlines() if x]
    by = defaultdict(list)
    for r in recs:
        by[r["strategy"]].append(r)
    rows_out, fail_rows = [], []
    for strategy in STRATEGIES:
        rs = by.get(strategy, [])
        turns = [t for r in rs for t in r["turns"]]
        n = len(turns)
        sc = [t["score"] for t in turns]
        answered = [t for t in turns if t["score"]["kind_ok"] is not None]
        owe_scored = [t for t in answered if t["score"]["owe_ok"] is not None]
        claims = sum(s["claims"] for s in sc)
        met = sum(s["claims_met"] for s in sc)
        cites = sum(len(t["pred"].get("citations") or []) for t in turns)
        inv = sum(len(s["invented"]) for s in sc)
        rows_out.append({
            "strategy": strategy,
            "turns": n,
            "turn_accuracy_pct": pct(sum(t["correct"] for t in turns), n),
            "scenario_accuracy_pct": pct(sum(all(t["correct"] for t in r["turns"]) for r in rs), len(rs)),
            "outcome_accuracy_pct": pct(sum(s["outcome_ok"] for s in sc), n),
            "amount_accuracy_pct": pct(sum(bool(t["score"]["owe_ok"]) for t in owe_scored), len(owe_scored)),
            "citation_coverage_pct": pct(met, claims),
            "invented_citation_pct": pct(inv, cites),
            "valid_json_first_try_pct": pct(sum(t["stats"]["first_try_valid"] for t in turns), n),
            "invalid_json_turns": sum(t["stats"]["error"] == "invalid_json" for t in turns),
            "calls": sum(t["stats"]["calls"] for t in turns),
            "tokens_per_turn": round(statistics.mean(t["stats"]["tokens"] for t in turns)) if turns else 0,
            "seconds_per_turn": round(statistics.mean(t["stats"]["seconds"] for t in turns), 2) if turns else 0,
        })  # fmt: skip
        for r in rs:
            for t in r["turns"]:
                if not t["correct"]:
                    labels = list(t["score"]["labels"])
                    if t["stats"]["error"] == "invalid_json":
                        labels.insert(0, "invalid_json")
                    fail_rows.append({
                        "strategy": strategy, "id": r["id"], "category": r["category"], "turn": t["turn"],
                        "labels": ";".join(labels) or "other",
                        "pred_outcome": t["pred"].get("outcome"), "pred_owe": t["pred"].get("owe_usd"),
                        "pred_citations": "; ".join(t["pred"].get("citations") or []),
                        "invented": "; ".join(t["score"]["invented"]),
                    })  # fmt: skip
    for mode in INTAKE_MODES:
        rs = by.get(mode, [])
        f = sum(r["extraction"]["fields"] for r in rs)
        c = sum(r["extraction"]["correct"] for r in rs)
        rows_out.append({
            "strategy": mode, "turns": len(rs), "turn_accuracy_pct": "", "scenario_accuracy_pct": "",
            "outcome_accuracy_pct": "", "amount_accuracy_pct": "", "citation_coverage_pct": "",
            "invented_citation_pct": "", "extraction_field_accuracy_pct": pct(c, f),
            "invented_fields": sum(r["extraction"]["invented"] for r in rs),
            "valid_json_first_try_pct": pct(sum(r["stats"]["first_try_valid"] for r in rs), len(rs)),
            "invalid_json_turns": sum(r["stats"]["error"] == "invalid_json" for r in rs),
            "calls": sum(r["stats"]["calls"] for r in rs),
            "tokens_per_turn": round(statistics.mean(r["stats"]["tokens"] for r in rs)) if rs else 0,
            "seconds_per_turn": round(statistics.mean(r["stats"]["seconds"] for r in rs), 2) if rs else 0,
        })  # fmt: skip
    fields = list(dict.fromkeys(k for r in rows_out for k in r))
    with (OUT / "week1_strategies.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows_out)
    with (OUT / "week1_failures.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=list(fail_rows[0]) if fail_rows else ["strategy"], lineterminator="\n"
        )
        w.writeheader()
        w.writerows(fail_rows)
    label_counts = defaultdict(Counter)
    for f in fail_rows:
        for lab in f["labels"].split(";"):
            label_counts[f["strategy"]][lab.split(":")[0]] += 1
    intro = (
        f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC by `eval.baseline`. Qwen3-8B "
        "on the upgrad endpoint, single prompts, no tools, no calculators, no retrieval. Scored by "
        "`eval/score.py`. *Invented cites* = cited regulation sections that are not in the corpus "
        "snapshot (fabricated, or real but outside the snapshot). Amount % is over answered turns "
        "where the gold has an amount; citation cover % is gold citation claims met."
    )
    header = (
        "| Strategy | Turns | Turn acc % | Scenario acc % | Outcome % | Amount % | Citation cover % "
        "| Invented cites % | Valid JSON 1st try % | Tokens/turn | s/turn |"
    )
    md = ["# Week-1 baselines (eval-v1, bare model)", "", intro, "", header,
          "|---|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for r in rows_out[: len(STRATEGIES)]:
        md.append(
            f"| {r['strategy']} | {r['turns']} | {r['turn_accuracy_pct']} | {r['scenario_accuracy_pct']} "
            f"| {r['outcome_accuracy_pct']} | {r['amount_accuracy_pct']} | {r['citation_coverage_pct']} "
            f"| {r['invented_citation_pct']} | {r['valid_json_first_try_pct']} | {r['tokens_per_turn']} "
            f"| {r['seconds_per_turn']} |"
        )
    md += ["", "| Intake | Scenarios | Field accuracy % | Invented fields | Valid JSON 1st try % | Invalid |",
           "|---|---|---|---|---|---|"]  # fmt: skip
    for r in rows_out[len(STRATEGIES) :]:
        md.append(
            f"| {r['strategy']} | {r['turns']} | {r['extraction_field_accuracy_pct']} | "
            f"{r['invented_fields']} | {r['valid_json_first_try_pct']} | {r['invalid_json_turns']} |"
        )
    md += ["", "## Failure labels per strategy", ""]
    for s, cnt in label_counts.items():
        md.append(f"- **{s}**: " + ", ".join(f"{k} {v}" for k, v in cnt.most_common()))
    (OUT / "week1-baselines.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="exact call count; send nothing")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--who", help="who ran it (quota log); required to call the endpoint")
    parser.add_argument("--limit", type=int, help="first N scenarios only")
    args = parser.parse_args()
    rows = load_rows("queries.jsonl")[: args.limit]
    if args.report_only:
        report()
        return
    done = done_keys()
    todo = [r for r in rows if any((r["id"], s) not in done for s in [*STRATEGIES, *INTAKE_MODES])]
    print(f"{len(rows)} scenarios, {sum(len(r['turns']) for r in rows)} turns; "
          f"planned calls (before JSON retries): {count_calls(rows)}; still to run: {len(todo)} scenarios")  # fmt: skip
    if args.dry_run:
        print("dry run: nothing sent")
        return
    if not args.who:
        print("FAIL calling the upgrad chat endpoint needs --who (quota log)", file=sys.stderr)
        sys.exit(1)
    settings = get_settings()
    tracer = Tracer(settings)
    runner = Runner(ChatClient(settings, tracer=tracer))
    t0 = time.time()
    calls, tokens = run(args.who, rows, runner, tracer)
    append_quota_log(
        args.who, "baselines (eval-v1, 4 strategies + intake comparison)", calls, 0, tokens,
        f"run took {round((time.time() - t0) / 60)} min",
    )  # fmt: skip
    report()


if __name__ == "__main__":
    main()
