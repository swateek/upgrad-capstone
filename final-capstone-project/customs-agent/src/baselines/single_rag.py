"""single_rag baseline (ablation arm): retrieve, then one model call answers from the clauses.

No guard, no intake, no calculators, no planner, no verifier: the Day-4 TASK prompt plus the top 5
clauses from the same search the agent uses (hybrid + bge reranker, hard negatives filtered), with
free-text search only (there are no tools to say which rules apply). Compared with closed_book it
measures what retrieval adds; compared with the router, what the tools and code add.
"""

from __future__ import annotations

from typing import Any

from src.baselines import prompts
from src.baselines.answer import Answer
from src.baselines.strategies import Run, StepError, call
from src.schemas import Clause

SINGLE_RAG = (
    prompts.TASK
    + """

You are given regulation clauses retrieved for this question, each with its id in [brackets]. Base the answer on them, and cite only those ids."""
)


def render(clauses: list[Clause]) -> str:
    return "\n\n".join(f"[{c.citation_id}] {c.heading}\n{c.text}" for c in clauses)


def single_rag(
    llm: Any, search: Any, question: str, inject: dict | None = None
) -> tuple[Run, list[str], dict]:
    """Returns (run, retrieved ids, trace entry)."""
    from src.tools.search_regulations import Args as SearchArgs

    run = Run()
    found = search(SearchArgs(query=question, citation_ids=[]))
    clauses = list(found.clauses)
    if inject:  # injection_doc scenarios: planted among the results, as for the agent (no sanitiser)
        clauses.insert(
            0,
            Clause(
                citation_id=inject["doc_id"],
                chunk_id=f"{inject['doc_id']}#01",
                heading="",
                text=inject["text"],
                authority="agency_guidance",
                found_by="search",
                rank=1,
            ),
        )
    ids = list(dict.fromkeys(c.citation_id for c in clauses))
    trace = {"step": "search_regulations", "retrieved": ids, "method": found.method}
    msgs = [
        {"role": "system", "content": SINGLE_RAG},
        {
            "role": "user",
            "content": f"Question: {question}\n\nRegulation clauses:\n{render(clauses)}",
        },
    ]
    try:
        run.answer = call(llm, run, Answer, msgs, stage="baseline_single_rag")
    except StepError as e:
        run.error = str(e)
    return run, ids, trace
