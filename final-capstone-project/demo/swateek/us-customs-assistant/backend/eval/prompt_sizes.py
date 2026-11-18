"""Prompt sizes per node, measured offline on the DEV scenarios (plan step 9: "prompt-size
measurement"). Builds each node's real prompt from the dev gold facts (the calculators' real
figures, real source texts fetched by clause id) and counts tokens with the Qwen3 tokenizer.
No model call and no embedding call.

    uv run python -m eval.prompt_sizes      # -> docs/results/prompt-sizes.md
"""

from __future__ import annotations

import json
import statistics

from customs.agent import card as cards
from customs.agent import intake, planner, rag, tool_calling, verifier, writer
from customs.agent.executor import finalise
from customs.config import PROJECT_ROOT, get_settings
from customs.llm.budget import count_message_tokens, get_tokenizer
from customs.retrieval.service import RegulationSearch
from customs.tools.calc import (
    new_case,
    step_allowance,
    step_duty_excise,
    step_exemption,
    step_normalise,
    step_restrictions,
)
from customs.tools.models import Line, Profile
from customs.tools.tables import load_tables

DEV = PROJECT_ROOT / "pack" / "eval" / "dev.jsonl"
OUT = PROJECT_ROOT / "docs" / "results" / "prompt-sizes.md"


def sys_msg(path) -> dict:
    return {"role": "system", "content": path.read_text(encoding="utf-8").strip()}


def measure() -> tuple[dict[str, list[int]], dict[str, int], list[int]]:
    s = get_settings()
    tok = get_tokenizer(s.tokenizer_id)
    t = load_tables()
    search = RegulationSearch(s, rankings=lambda qs, fs: [[] for _ in qs], tables=t)  # by id only
    sizes: dict[str, list[int]] = {k: [] for k in
                                   ("intake", "intake_followup", "planner", "writer", "review",
                                    "executor_first_round", "single_rag")}  # fmt: skip
    per_question: list[int] = []
    windows = [json.loads(x) for x in (s.data_dir / "chunks" / "window200.jsonl").open()][:5]
    for line in DEV.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        f = row["facts"]
        profile = Profile.model_validate(f["profile"])
        basket = [Line.model_validate(x) for x in f["basket"]]
        q = " ".join(row["turns"])

        def n(msgs, tools=None):
            return count_message_tokens(tok, msgs, tools)

        m_in = [
            sys_msg(intake.PROMPT),
            {"role": "user", "content": intake.user_content(q, None, None)},
        ]
        sizes["intake"].append(n(m_in))
        m_in2 = [sys_msg(intake.PROMPT),
                 {"role": "user", "content": intake.user_content(row["turns"][-1], f, "Are you 21 or older?")}]  # fmt: skip
        sizes["intake_followup"].append(n(m_in2))
        block = "\n\n".join(f"[{w['clause_ids'][0]}] {w['citation']}: {w['text']}" for w in windows)
        sizes["single_rag"].append(n([sys_msg(rag.PROMPT), {"role": "user", "content": f"Passages:\n{block}"},
                                      {"role": "user", "content": q}]))  # fmt: skip
        if not basket:
            continue
        case = new_case(profile, basket, t)
        step_normalise(case)
        step_restrictions(case)
        m_pl = [sys_msg(planner.PROMPT), {"role": "user", "content": planner.describe_case(case)}]
        sizes["planner"].append(n(m_pl))
        tc_msgs = [sys_msg(tool_calling.PROMPT),
                   {"role": "user", "content": "Facts: " + json.dumps(f) + "\n\nPlan: " +
                    ", ".join(st.step for st in planner.router_plan(case).steps)}]  # fmt: skip
        sizes["executor_first_round"].append(n(tc_msgs, tool_calling.tool_specs()))
        if case.admissible:
            step_exemption(case)
            step_allowance(case)
            step_duty_excise(case)
        a = finalise(case)
        if a.outcome != "answered":
            continue
        sources, _ = search.search(q, a.rule_refs)
        figs = cards.figure_rows(a.figures, a.lines)
        m_wr = [sys_msg(writer.PROMPT),
                {"role": "user", "content": writer.writer_input(q, a, figs, sources)}]  # fmt: skip
        sizes["writer"].append(n(m_wr))
        srcs = "\n".join(f"{x.handle} {x.citation}: {x.text}" for x in sources)
        m_rv = [{"role": "system", "content": verifier.REVIEW_SYSTEM},
                {"role": "user", "content": f"Sources:\n{srcs}\n\nSentences:\n1. x\n2. y\n3. z\n4. w"}]  # fmt: skip
        sizes["review"].append(n(m_rv))
        per_question.append(
            sizes["intake"][-1]
            + intake.MAX_TOKENS
            + sizes["planner"][-1]
            + planner.MAX_TOKENS
            + sizes["writer"][-1]
            + writer.MAX_TOKENS
            + sizes["review"][-1]
            + verifier.REVIEW_TOKENS
        )
    caps = {"intake": intake.MAX_TOKENS, "intake_followup": intake.MAX_TOKENS,
            "planner": planner.MAX_TOKENS, "writer": writer.MAX_TOKENS,
            "review": verifier.REVIEW_TOKENS, "executor_first_round": tool_calling.MAX_TOKENS,
            "single_rag": rag.MAX_TOKENS}  # fmt: skip
    return sizes, caps, per_question


def main() -> None:
    sizes, caps, per_q = measure()
    s = get_settings()
    lines = [
        "# Prompt sizes per node (dev scenarios, offline)",
        "",
        (
            "Generated by `eval/prompt_sizes.py` from the dev gold facts with the Qwen3-8B tokenizer "
            "(estimator +7 per message, +85 with tools). Real figures and real source texts (fetched "
            "by clause id), so the writer's size is what it will be. No model or embedding call."
        ),
        "",
        (
            f"Window per call: {s.context_window_tokens:,} tokens (prompt + max_tokens). Budget per "
            f"question: {s.agent_token_limit:,} tokens; target under ~3k input tokens per call (§4.6)."
        ),
        "",
        "| node | n | prompt min | mean | max | max_tokens | worst call vs 8K window |",
        "|---|---|---|---|---|---|---|",
    ]
    for k, v in sizes.items():
        if v:
            worst = max(v) + caps[k]
            lines.append(f"| {k} | {len(v)} | {min(v):,} | {statistics.mean(v):,.0f} | {max(v):,} "
                         f"| {caps[k]} | {worst:,} ({worst / s.context_window_tokens:.0%}) |")  # fmt: skip
    if per_q:
        lines += [
            "",
            (
                "**Per answered question, worst case** (intake + planner + writer + review, each at "
                f"its full max_tokens): min {min(per_q):,}, mean {statistics.mean(per_q):,.0f}, max "
                f"{max(per_q):,} tokens, against the {s.agent_token_limit:,} budget. Actual use is "
                "lower: replies rarely reach max_tokens. A verifier rewrite adds one writer call; a "
                "replan adds one planner call. `tool_calling` adds one executor round per step, each "
                "resending the conversation so far."
            ),
        ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
