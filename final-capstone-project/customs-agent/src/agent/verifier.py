"""Verifier (code + one LLM call): the writer's text against the tool outputs.

Code checks (CLAUDE.md rules 1-2):
  - every number (dollar amounts included) appears in the tool outputs, the retrieved clauses,
    the facts or the question: a computed amount the calculators did not produce is rejected;
  - the bottom line states the total owed when something is owed;
  - sources point at clauses that were retrieved;
  - no evasion wording.
LLM check: does the text advise evasion? (one short call; off in unit tests).
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel

from src.agent import prompts
from src.agent.llm_json import StepError, Usage, json_call
from src.agent.writer import WriterOut
from src.safety.guard import EVASION

NUMBER = re.compile(r"(\$\s?)?(\d[\d,]*(?:\.\d+)?)")


def _num(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace(",", "")).normalize()
    except InvalidOperation:
        return None


def numbers(text: str) -> tuple[set[Decimal], set[Decimal]]:
    """(dollar amounts, all numbers) in a text."""
    dollars, every = set(), set()
    for m in NUMBER.finditer(text or ""):
        n = _num(m.group(2).rstrip(".,"))
        if n is None:
            continue
        every.add(n)
        if m.group(1):
            dollars.add(n)
    return dollars, every


def allowed_numbers(sources: list[str]) -> set[Decimal]:
    """Numbers the writer may state: those in the tool outputs (search_regulations included: the
    retrieved clauses carry thresholds such as $800 or $1,000), the facts and the question. A computed
    amount can only come from the calculators, because no clause or fact contains it."""
    every: set[Decimal] = set()
    for s in sources:
        every |= numbers(s)[1]
    every |= {
        (e * 100).normalize() for e in every if 0 < e < 1
    }  # rates as fractions: 0.03 -> 3%
    return every


def _sentence_with(text: str, n: Decimal) -> str:
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if n in numbers(sent)[1]:
            return sent.strip()
    return text[:120]


class EvasionCheck(BaseModel):
    advises_evasion: bool


def verify(
    out: WriterOut,
    *,
    n_clauses: int,
    tool_json: str,
    facts_text: str,
    question: str,
    clause_texts: list[str],
    total_owed: Decimal | None,
    llm: Any = None,
    usage: Usage | None = None,
) -> list[str]:
    problems: list[str] = []
    text = f"{out.bottom_line}\n{out.explanation}"
    ok = allowed_numbers([tool_json, facts_text, question, *clause_texts])
    got_dollars, got_all = numbers(text)
    for n in sorted(got_all - ok):
        what = f"${n}" if n in got_dollars else f"the number {n}"
        problems.append(
            f'{what} in "{_sentence_with(text, n)}" is not in the result or working: '
            "copy the numbers from WORKING exactly instead of working them out"
        )
    if (
        total_owed is not None
        and total_owed > 0
        and total_owed.normalize() not in numbers(out.bottom_line)[0]
    ):
        problems.append(
            f"the bottom line must state the total owed, ${total_owed:,.2f}"
        )
    bad = [s for s in out.sources if not 1 <= s <= n_clauses]
    if bad:
        problems.append(f"sources {bad} are not clause numbers (1 to {n_clauses})")
    if EVASION.search(text):
        problems.append(
            "remove wording about hiding or not declaring; tell them to declare"
        )
    if not problems and llm is not None and usage is not None:
        try:
            chk = json_call(
                llm,
                usage,
                EvasionCheck,
                [
                    {"role": "system", "content": prompts.VERIFY_EVASION},
                    {"role": "user", "content": text},
                ],
                stage="verifier",
                max_tokens=30,
            )
            if chk.advises_evasion:
                problems.append(
                    "the answer must not advise evasion; tell them to declare"
                )
        except StepError as e:
            problems.append(f"evasion check failed: {e}")
    return problems


def tool_json(objs: list[object]) -> str:
    return json.dumps(
        [o.model_dump(mode="json") if hasattr(o, "model_dump") else o for o in objs],
        ensure_ascii=False,
    )


def prune(out: WriterOut, sources: list[str]) -> tuple[WriterOut, list[str]]:
    """Drop the explanation's sentences that state a number no tool, fact, clause or the question
    gave (agent v2): after the writer's retry, a correct answer with one invented sentence ("only
    $300 of it is available for alcohol", dev-v2 D2-064) is kept without that sentence instead of
    escalated. Returns the pruned output and the sentences removed."""
    ok = allowed_numbers(sources)
    keep, removed = [], []
    for sent in re.split(r"(?<=[.!?])\s+", out.explanation or ""):
        (removed if numbers(sent)[1] - ok else keep).append(sent)
    return out.model_copy(update={"explanation": " ".join(keep).strip()}), removed
