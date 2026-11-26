"""Writer: one LLM call that explains the code-built answer card in plain English (JSON)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from src.agent import prompts
from src.agent.llm_json import Usage, json_call
from src.baselines.answer import Strict
from src.schemas import Clause


class WriterOut(Strict):
    bottom_line: str = Field(description="One sentence: the result for each item")
    explanation: str = Field(description="Under 100 words, plain English")
    sources: list[int] = Field(
        default_factory=list,
        description="Numbers of the clauses that support the explanation",
    )


def render_clauses(clauses: list[Clause]) -> str:
    return "\n\n".join(
        f"[{i}] {c.citation_id} | {c.heading}\n{c.text}"
        for i, c in enumerate(clauses, start=1)
    )


def write(
    llm: Any,
    usage: Usage,
    *,
    question: str,
    result: list[str],
    working: list[str],
    facts: list[str],
    clauses: list[Clause],
    feedback: list[str] | None = None,
) -> WriterOut:
    body = (
        f"Traveller's question: {question}\n\n"
        "RESULT:\n" + "\n".join(f"- {x}" for x in result) + "\n\n"
        "WORKING:\n" + "\n".join(f"- {x}" for x in working) + "\n\n"
        "FACTS RELIED ON:\n" + "\n".join(f"- {x}" for x in facts) + "\n\n"
        "CLAUSES:\n" + render_clauses(clauses)
    )
    msgs = [
        {"role": "system", "content": prompts.WRITER},
        {"role": "user", "content": body},
    ]
    if feedback:
        msgs.append(
            {
                "role": "user",
                "content": "Your previous answer failed these checks; fix them:\n"
                + "\n".join(f"- {f}" for f in feedback),
            }
        )
    return json_call(llm, usage, WriterOut, msgs, stage="writer", max_tokens=500)
