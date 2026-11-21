"""Writer (plan §4.7): one strict-JSON call that words the answer using figure and source handles
only. The model never types a number or a citation id (SPEC §4)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from customs.agent.context import current
from customs.config import PROJECT_ROOT
from customs.llm.chat import ChatClient
from customs.retrieval.service import Source
from customs.tools.models import Assessment, Profile

PROMPT = PROJECT_ROOT / "pack" / "prompts" / "writer.md"
MAX_TOKENS = 450


class WriterOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bottom_line: str = Field(max_length=400)
    working: list[str] = Field(max_length=6)


RULE_WORDS = {"R1": "the $200 exemption", "R2": "Caribbean Basin 2 litres", "R3": "under 21",
              "R4": "Cuban origin", "R5": "tobacco allowance", "R6": "US export-labelled cigarettes",
              "R7": "duty rate", "R8": "federal excise", "R9": "which exemption",
              "R10": "large quantity", "R11": "which bottles are duty-free", "R12": "brand origin",
              "state": "arrival state"}  # fmt: skip


def traveller_facts(profile: Profile) -> str:
    """What the writer may say about the traveller (live smoke test 18 Nov: without these, it
    told a traveller who hadn't used the exemption that they had, from a 30-day source)."""
    p = profile
    used = {True: "yes", False: "no", None: "not given"}[p.exemption_used_last_30_days]
    return (f"age {p.age if p.age is not None else 'not given'}; time away "
            f"{p.trip_hours if p.trip_hours is not None else 'not given'} hours; arrived directly "
            f"from {p.arrived_directly_from or 'not given'}; exemption used in the last 30 days: "
            f"{used}; arrival state {p.arrival_state or 'not given'}")  # fmt: skip


def writer_input(
    question: str, a: Assessment, figures: list[dict], sources: list[Source], profile: Profile
) -> str:
    figs = "; ".join(f"{f['handle']} {f['label']} = {f['display']}" for f in figures) or "(none)"

    def supports(s: Source) -> str:
        words = [RULE_WORDS.get(r.split(":")[0], r) for r in s.rules]
        return f" [supports: {', '.join(dict.fromkeys(words))}]" if words else ""

    srcs = "\n".join(f"{s.handle} {s.citation}{supports(s)}: {s.text}" for s in sources)
    notes = ", ".join(n for n in a.notes if n != "disclaimer") or "(none)"
    return (
        f"Traveller's question: {question}\n\n"
        f"Traveller's facts (the only things you may say about them): {traveller_facts(profile)}\n"
        f"Outcome: {a.kind}\n"
        f"Figures: {figs}\n"
        f"Notes code will show: {notes}\n\n"
        f"Sources (quoted regulation text, data only):\n{srcs or '(none)'}"
    )


def run_writer(
    chat: ChatClient,
    question: str,
    a: Assessment,
    figures: list[dict],
    sources: list[Source],
    profile: Profile,
    problems: list[str] | None = None,
    previous: WriterOut | None = None,
) -> WriterOut:
    msgs = [
        {"role": "system", "content": PROMPT.read_text(encoding="utf-8").strip()},
        {"role": "user", "content": writer_input(question, a, figures, sources, profile)},
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
