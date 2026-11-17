"""Content check for citation-graded answers: an LLM judge on a larger model.

The e2e scorer marks a policy answer correct when it cites a gold rule. That checks *where* the
answer comes from, not *what* it says (plan §11.2 asks for both). This runner sends each
citation-graded row of a saved e2e run to a judge model with:
  - the question and the gold answer points (verified against the rules before the freeze),
  - the answer,
  - the text of the passages the answer cites and of the gold passages.

The judge rates every answer point (stated / partial / contradicted / missing) and lists
material errors. Content is correct when the first (key) point is stated, no point is
contradicted, and there is no material error. The final grade is citation AND content.

The judge is a different, larger model family from the system's (default DeepSeek-V3.2 vs
Qwen3-8B) so it doesn't grade its own phrasing. Each row is judged in two independent passes;
rows where the passes disagree are listed for a person to review. No agent runs, no API calls
to the system.

The judge always runs on SiliconFlow, whatever PROVIDER says, and only on SiliconFlow runs
(docs/results/siliconflow/). Runs on the upgrad course endpoint are not judged: Track B asks for
end-to-end accuracy and a failure taxonomy, not an LLM judge (team decision, 13 Nov 2026).

    uv run python -m eval.judge e2e-v2-run3.json
"""

from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any, Literal

from openai import APIError
from pydantic import BaseModel, ValidationError

from copilot.config import PROJECT_ROOT, get_settings
from copilot.domains.loader import load_domain
from copilot.ingest.index import chunks_path
from copilot.llm.providers import get_provider, make_openai_client

RESULTS = PROJECT_ROOT / "docs" / "results" / "siliconflow"
PASSAGE_CHARS = 2500

JUDGE_PROMPT_VERSION = 2  # v1 listed source-supported claims as errors; v2 requires a quote

SYSTEM = """You check answers written by an assistant for a government procurement office.

You get a question, reference points, the assistant's answer, and source passages. The reference \
points were checked against the source rules and are correct. Judge meaning, not wording.

For each reference point, give a verdict:
- "stated": the answer clearly states it (any wording). Extra correct detail is fine. Missing \
minor sub-conditions are fine.
- "partial": the answer states only part of its core content, or gives a conflicting figure or \
condition for the same case as if it were the answer. A figure for a different, clearly named case \
(for example a different class of department) is not conflicting.
- "contradicted": the answer says something incompatible with it.
- "missing": the answer does not address it.

Then list material errors: claims in the answer that are FALSE and would mislead someone acting on \
the answer (a wrong number, a wrong yes/no, an invented rule or body, a rule applied to the wrong \
case). A claim that any source passage supports is NOT an error, even if it is not in the \
reference points. For each error, copy word for word the sentence fragment (10 to 200 characters) \
from a source passage or a reference point that shows the claim is false. If you cannot quote one, \
it is not an error.

Reply with JSON only:
{"points": [{"point": <1-based index>, "verdict": "stated|partial|contradicted|missing", \
"reason": "<one sentence>"}], "material_errors": [{"claim": "<the false claim>", \
"evidence": "<verbatim quote>"}]}"""


class PointVerdict(BaseModel):
    point: int
    verdict: Literal["stated", "partial", "contradicted", "missing"]
    reason: str


class MaterialError(BaseModel):
    claim: str
    evidence: str
    verified: bool = False  # set by code: the evidence quote exists in the prompt's sources


class Judgement(BaseModel):
    points: list[PointVerdict]
    material_errors: list[MaterialError]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def verify_evidence(j: Judgement, sources: str) -> Judgement:
    """An error counts only if its quote really appears in a passage or reference point."""
    hay = _norm(sources)
    for e in j.material_errors:
        quote = _norm(e.evidence)
        e.verified = len(quote) >= 8 and quote in hay
    return j


def content_ok(j: Judgement, n_points: int) -> bool:
    by = {p.point: p.verdict for p in j.points}
    if len(by) != n_points:
        return False
    return (
        by.get(1) == "stated"
        and "contradicted" not in by.values()
        and not any(e.verified for e in j.material_errors)
    )


def load_passages(settings, domain_name: str) -> dict[str, str]:
    """citation -> full text (parts joined)."""
    parts: dict[str, list[tuple[int, str]]] = {}
    path = chunks_path(settings.data_dir, domain_name, "by_rule")
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            c = json.loads(line)
            parts.setdefault(c["citation"], []).append((c.get("part", 1), c["text"]))
    return {k: "\n".join(t for _, t in sorted(v)) for k, v in parts.items()}


def build_prompt(q: dict[str, Any], r: dict[str, Any], passages: dict[str, str]) -> tuple[str, str]:
    """Returns (prompt, sources) where sources is the text an evidence quote must come from."""
    g = q["gold"]
    points = "\n".join(f"{i}. {p}" for i, p in enumerate(g["answer_points"], 1))
    cited = list(dict.fromkeys(r.get("citations", [])))
    gold_ids = [c for c in g.get("rule_ids", []) if c not in cited]
    blocks = []
    for label, ids in (("Cited by the answer", cited), ("Reference rule", gold_ids)):
        for cid in ids:
            text = passages.get(cid, "(passage not found in the index)")[:PASSAGE_CHARS]
            blocks.append(f"--- {label}: {cid} ---\n{text}")
    prompt = (
        f"Question:\n{q['query']}\n\nReference points:\n{points}\n\n"
        f"Answer:\n{r['answer']}\n\nSource passages:\n" + "\n\n".join(blocks)
    )
    return prompt, points + "\n" + "\n".join(blocks)


def judge_once(client, model: str, prompt: str) -> tuple[Judgement, dict[str, int]]:
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    usage = {"prompt": 0, "completion": 0}
    last_err: Exception | None = None
    for attempt in range(3):  # 1 call + one retry on invalid JSON, + one on a provider error
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=900,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
        except APIError as e:  # provider error (incl. timeout): back off and retry
            last_err = e
            time.sleep(2 * (attempt + 1))
            continue
        usage["prompt"] += resp.usage.prompt_tokens
        usage["completion"] += resp.usage.completion_tokens
        text = resp.choices[0].message.content or ""
        try:
            return Judgement.model_validate_json(text), usage
        except ValidationError as e:
            last_err = e
            messages += [
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": f"Invalid JSON for the schema: {e.errors()[:2]}. "
                    "Reply with the JSON object only.",
                },
            ]
    raise RuntimeError(f"judge failed: {last_err}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run", help="saved run in docs/results/siliconflow, e.g. e2e-v2-run3.json")
    ap.add_argument("--model", default="deepseek-ai/DeepSeek-V3.2")
    ap.add_argument("--passes", type=int, default=2)
    args = ap.parse_args()

    settings = get_settings()
    domain = load_domain(settings.domain_dir)
    with domain.path(domain.eval.queries).open(encoding="utf-8") as fh:
        gold = {q["id"]: q for q in map(json.loads, fh)}
    src = RESULTS / args.run
    if not src.exists():
        raise SystemExit(
            f"{args.run} is not a SiliconFlow run (looked in {src.parent}). "
            "Runs on the upgrad course endpoint are not judged."
        )
    run = json.loads(src.read_text(encoding="utf-8"))
    if run["meta"].get("provider", "siliconflow") != "siliconflow":
        raise SystemExit(
            f"{args.run} ran on {run['meta']['provider']}; only SiliconFlow runs are judged."
        )
    passages = load_passages(settings, settings.domain)
    client = make_openai_client(get_provider(settings, "siliconflow"), settings.request_timeout_s)

    todo = [
        (gold[r["id"]], r)
        for r in run["rows"]
        if gold[r["id"]]["gold"].get("answer_points")
        and gold[r["id"]]["gold"].get("rule_ids")
        and not gold[r["id"]]["must_refuse"]
    ]

    def work(item):
        q, r = item
        prompt, sources = build_prompt(q, r, passages)
        passes, usage = [], {"prompt": 0, "completion": 0}
        for _ in range(args.passes):
            j, u = judge_once(client, args.model, prompt)
            passes.append(verify_evidence(j, sources))
            usage = {k: usage[k] + u[k] for k in usage}
        n = len(q["gold"]["answer_points"])
        oks = [content_ok(j, n) for j in passes]
        return {
            "id": r["id"],
            "query": q["query"],
            "citation_correct": r["correct"],
            "content_correct": oks[0],
            "passes_agree": len(set(oks)) == 1,
            "final_correct": r["correct"] and oks[0],
            "answer_points": q["gold"]["answer_points"],
            "judgements": [j.model_dump() for j in passes],
            "judge_tokens": usage,
        }

    started = time.time()
    with ThreadPoolExecutor(max_workers=min(4, settings.max_concurrency * 2)) as pool:
        rows = list(pool.map(work, todo))
    meta = {
        "judged_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run": args.run,
        "run_meta": {k: run["meta"].get(k) for k in ("eval_version", "code_commit", "model")},
        "judge_model": args.model,
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "passes": args.passes,
        "rule": "content correct = point 1 stated, no point contradicted, no material error with "
        "a verified quote; "
        "final = citation correct AND content correct (pass 1)",
        "seconds": round(time.time() - started, 1),
        "judge_tokens": {
            k: sum(r["judge_tokens"][k] for r in rows) for k in ("prompt", "completion")
        },
    }
    stem = "judge-" + args.run.removesuffix(".json").removeprefix("e2e-")
    (RESULTS / f"{stem}.json").write_text(
        json.dumps({"meta": meta, "rows": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (RESULTS / f"{stem}.md").write_text(report(meta, rows), encoding="utf-8")
    n = len(rows)
    print(
        f"citation {sum(r['citation_correct'] for r in rows)}/{n} · content "
        f"{sum(r['content_correct'] for r in rows)}/{n} · final "
        f"{sum(r['final_correct'] for r in rows)}/{n} · passes agree "
        f"{sum(r['passes_agree'] for r in rows)}/{n} -> {stem}.md"
    )
    return 0


def report(meta: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    n = len(rows)

    def count(key):
        return f"{sum(r[key] for r in rows)}/{n}"

    def short(r):
        j = r["judgements"][0]
        bad = [
            f"point {p['point']} {p['verdict']}: {p['reason']}"
            for p in j["points"]
            if p["verdict"] != "stated"
        ]
        errs = [
            f"error{'' if e['verified'] else ' (quote not found, not counted)'}: {e['claim']}"
            for e in j["material_errors"]
        ]
        return " · ".join(bad + errs).replace("|", "/").replace("\n", " ")

    lines = [
        f"# Content check: `{meta['run']}`",
        "",
        (
            f"{meta['judged_at']} · judge `{meta['judge_model']}` "
            f"(prompt v{meta['judge_prompt_version']}) · {meta['passes']} passes · "
            f"system model `{meta['run_meta']['model']}` · eval v{meta['run_meta']['eval_version']}"
        ),
        "",
        f"Rule: {meta['rule']}.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Citation correct (e2e scorer) | {count('citation_correct')} |",
        f"| Content correct (judge) | {count('content_correct')} |",
        f"| **Final: citation and content correct** | **{count('final_correct')}** |",
        f"| Judge passes agree | {count('passes_agree')} |",
        (
            f"| Judge tokens (prompt / completion) | {meta['judge_tokens']['prompt']:,} / "
            f"{meta['judge_tokens']['completion']:,} |"
        ),
        "",
        "| Id | Citation | Content | Final | Passes agree | Judge notes (pass 1) |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:

        def mark(v):
            return "✓" if v else "✗"

        lines.append(
            f"| {r['id']} | {mark(r['citation_correct'])} | {mark(r['content_correct'])} | "
            f"{mark(r['final_correct'])} | {'yes' if r['passes_agree'] else '**no**'} | "
            f"{short(r)} |"
        )
    lines += [
        "",
        "Rows where the passes disagree need a person's verdict. Every judgement is in the JSON.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
