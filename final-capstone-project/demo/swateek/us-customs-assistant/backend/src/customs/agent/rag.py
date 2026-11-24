"""`single_rag` mode (plan §4.3): guard -> hybrid retrieval top-5 on the question alone -> one
answer call. No intake, no tools, no calculators, no verifier: the plain-RAG ablation that
the agent is compared with."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from customs.agent.card import Card
from customs.agent.context import current
from customs.config import PROJECT_ROOT
from customs.llm.chat import ChatClient
from customs.retrieval.service import RegulationSearch

PROMPT = PROJECT_ROOT / "pack" / "prompts" / "single_rag.md"
MAX_TOKENS = 500
TOP_K = 5


class RagAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    outcome: Literal["answered", "clarify", "refused", "out_of_scope", "escalated"]
    kind: Literal["owe", "nothing_owed", "prohibited", "seizure_risk", "mixed", "clarify",
                  "refused", "out_of_scope", "escalated"]  # fmt: skip
    owe_usd: float | None
    clarify_question: str | None
    citations: list[str]
    answer: str


def run_rag(chat: ChatClient, search: RegulationSearch, history: list[dict], message: str) -> Card:
    ctx = current()
    question = " ".join([*(h["content"] for h in history if h["role"] == "user"), message])
    before = search.embed_requests
    passages = search.top_passages(question, TOP_K)
    ctx.tool_call("search_regulations", {"sources": len(passages)})
    ctx.embed_requests += search.embed_requests - before
    block = "\n\n".join(f"[{p.clause_id}] {p.citation}: {p.text}" for p in passages)
    msgs = [
        {"role": "system", "content": PROMPT.read_text(encoding="utf-8").strip()},
        {"role": "user", "content": f"Passages:\n{block}"},
        *history,
        {"role": "user", "content": message},
    ]
    ctx.before_model_call()
    res = chat.complete(msgs, max_tokens=MAX_TOKENS, response_model=RagAnswer, name="single_rag")
    ctx.after_model_call("single_rag", res)
    a = res.parsed
    by_id = {p.clause_id: p for p in passages}
    return Card(
        outcome=a.outcome,
        kind=a.kind,
        bottom_line=a.answer,
        owe_usd=None if a.owe_usd is None else f"{a.owe_usd:.2f}",
        clarify_question=a.clarify_question,
        citations=list(a.citations),
        sources=[by_id[c].as_dict() for c in a.citations if c in by_id],
        meta={"passages": [p.clause_id for p in passages]},
    )
