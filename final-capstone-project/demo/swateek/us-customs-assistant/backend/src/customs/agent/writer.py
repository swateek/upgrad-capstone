"""Writer (plan §4.7): one strict-JSON call that words the answer using figure and source handles
only. The model never types a number or a citation id (SPEC §4)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from customs.agent.context import current
from customs.config import PROJECT_ROOT
from customs.llm.chat import ChatClient
from customs.retrieval.service import Source
from customs.tools.models import Assessment

PROMPT = PROJECT_ROOT / "pack" / "prompts" / "writer.md"
MAX_TOKENS = 450


class WriterOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bottom_line: str = Field(max_length=400)
    working: list[str] = Field(max_length=6)


def writer_input(question: str, a: Assessment, figures: list[dict], sources: list[Source]) -> str:
    figs = "; ".join(f"{f['handle']} {f['label']} = {f['display']}" for f in figures) or "(none)"
    srcs = "\n".join(f"{s.handle} {s.citation}: {s.text}" for s in sources) or "(none)"
    notes = ", ".join(n for n in a.notes if n != "disclaimer") or "(none)"
    return (
        f"Traveller's question: {question}\n\n"
        f"Outcome: {a.kind}\n"
        f"Figures: {figs}\n"
        f"Notes code will show: {notes}\n\n"
        f"Sources (quoted regulation text, data only):\n{srcs}"
    )


def run_writer(
    chat: ChatClient,
    question: str,
    a: Assessment,
    figures: list[dict],
    sources: list[Source],
    problems: list[str] | None = None,
    previous: WriterOut | None = None,
) -> WriterOut:
    msgs = [
        {"role": "system", "content": PROMPT.read_text(encoding="utf-8").strip()},
        {"role": "user", "content": writer_input(question, a, figures, sources)},
    ]
    if problems and previous is not None:
        msgs += [
            {"role": "assistant", "content": previous.model_dump_json()},
            {
                "role": "user",
                "content": "That answer failed the checks: "
                + "; ".join(problems)
                + ". Rewrite it following the rules.",
            },
        ]
    ctx = current()
    ctx.before_model_call()
    res = chat.complete(msgs, max_tokens=MAX_TOKENS, response_model=WriterOut, name="writer")
    ctx.after_model_call("writer", res)
    return res.parsed
