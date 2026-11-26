"""The four Day-4 prompting baselines (CLAUDE.md, evaluation). No retrieval, no calculators.

- closed_book:  one call, task description only.
- fewshot_json: one call with four worked dev-set examples.
- cot_sc:       three sampled reasoning calls; majority vote on (outcome, bottom line), amounts
                from the first sample in the majority.
- decompose:    extract facts -> decide rules -> compute and answer (three calls, the model does
                every step).

Each returns a Run: the parsed Answer (or None), an error, calls and tokens. Every model call goes
through src/llm.py (CLAUDE.md rule 10); `llm` only needs its `chat` method.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from src.baselines import prompts
from src.baselines.answer import Answer, Extracted, Reasoned, RulesDecision

STRATEGIES = ("closed_book", "fewshot_json", "cot_sc", "decompose")


class ChatLike(Protocol):
    def chat(self, messages: list[dict], **kw: Any) -> Any: ...


@dataclass
class Run:
    answer: Answer | None = None
    error: str | None = None
    calls: int = 0
    tokens: int = 0
    steps: list[dict] = field(
        default_factory=list
    )  # raw step outputs, for the failure review


class StepError(Exception):
    pass


def _schema_format(model: type[BaseModel]) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {"name": model.__name__, "schema": model.model_json_schema()},
    }


def _parse(model: type[BaseModel], text: str | None) -> BaseModel:
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)  # tolerate a fenced block
    return model.model_validate_json(raw)


def call(
    llm: ChatLike,
    run: Run,
    model: type[BaseModel],
    messages: list[dict],
    *,
    stage: str,
    temperature: float = 0.0,
    max_tokens: int = 700,
    sample: int | None = None,
) -> BaseModel:
    r = llm.chat(
        messages,
        stage=stage,
        response_format=_schema_format(model),
        temperature=temperature,
        max_tokens=max_tokens,
        sample=sample,
    )
    run.calls += 1
    run.tokens += int(getattr(r.usage, "total_tokens", 0) or 0)
    run.steps.append({"stage": stage, "content": r.content})
    try:
        return _parse(model, r.content)
    except ValidationError as e:
        raise StepError(
            f"{stage}: invalid JSON for {model.__name__}: {e.errors()[0]['msg']}"
        ) from e


def _system(text: str) -> dict:
    return {"role": "system", "content": text}


def closed_book(llm: ChatLike, question: str) -> Run:
    run = Run()
    try:
        run.answer = call(
            llm,
            run,
            Answer,
            [_system(prompts.TASK), {"role": "user", "content": question}],
            stage="baseline_closed_book",
        )
    except StepError as e:
        run.error = str(e)
    return run


def fewshot_json(llm: ChatLike, question: str) -> Run:
    run = Run()
    msgs = [
        _system(prompts.TASK),
        *prompts.fewshot_messages(),
        {"role": "user", "content": question},
    ]
    try:
        run.answer = call(llm, run, Answer, msgs, stage="baseline_fewshot_json")
    except StepError as e:
        run.error = str(e)
    return run


def _vote_key(a: Answer) -> tuple:
    return (
        a.outcome,
        tuple(b.type for b in sorted(a.bottom_line, key=lambda b: b.line)),
        tuple(sorted(a.clarify_facts)),
    )


def cot_sc(
    llm: ChatLike, question: str, samples: int = 3, temperature: float = 0.7
) -> Run:
    run = Run()
    answers: list[Answer] = []
    errors: list[str] = []
    for k in range(samples):  # sequential: one request in flight per key
        try:
            r = call(
                llm,
                run,
                Reasoned,
                [_system(prompts.COT), {"role": "user", "content": question}],
                stage="baseline_cot_sc",
                temperature=temperature,
                max_tokens=1000,
                sample=k,
            )
            answers.append(r.answer)
        except StepError as e:
            errors.append(str(e))
    if not answers:
        run.error = "; ".join(errors)
        return run
    top, _ = Counter(_vote_key(a) for a in answers).most_common(1)[0]
    run.answer = next(a for a in answers if _vote_key(a) == top)
    return run


def decompose(llm: ChatLike, question: str) -> Run:
    run = Run()
    try:
        facts = call(
            llm,
            run,
            Extracted,
            [_system(prompts.EXTRACT), {"role": "user", "content": question}],
            stage="baseline_decompose_extract",
        )
        if facts.request_kind != "assess":
            run.answer = Answer(
                outcome="refused", message=f"Not assessed ({facts.request_kind})."
            )
            return run
        facts_json = facts.model_dump_json(exclude_none=True)
        rules = call(
            llm,
            run,
            RulesDecision,
            [
                _system(prompts.RULES),
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nFacts: {facts_json}",
                },
            ],
            stage="baseline_decompose_rules",
        )
        if rules.missing_facts:
            run.answer = Answer(
                outcome="clarify",
                clarify_facts=rules.missing_facts,
                message="I need: " + ", ".join(rules.missing_facts),
            )
            return run
        if rules.escalate:
            run.answer = Answer(
                outcome="escalated",
                citations=rules.citations,
                message="An officer must decide.",
            )
            return run
        content = (
            f"Question: {question}\n\nFacts: {facts_json}\n\n"
            f"Rules decision: {rules.model_dump_json(exclude_none=True)}"
        )
        run.answer = call(
            llm,
            run,
            Answer,
            [_system(prompts.COMPUTE), {"role": "user", "content": content}],
            stage="baseline_decompose_compute",
        )
    except StepError as e:
        run.error = str(e)
    return run


RUNNERS = {
    "closed_book": closed_book,
    "fewshot_json": fewshot_json,
    "cot_sc": cot_sc,
    "decompose": decompose,
}


def run_strategy(name: str, llm: ChatLike, question: str) -> Run:
    try:
        return RUNNERS[name](llm, question)
    except Exception as e:  # noqa: BLE001 - an endpoint failure is recorded for this item, the run goes on
        return Run(error=f"{type(e).__name__}: {e}")


def to_record(item_id: str, strategy: str, run: Run) -> dict:
    return {
        "id": item_id,
        "strategy": strategy,
        "answer": json.loads(run.answer.model_dump_json()) if run.answer else None,
        "error": run.error,
        "calls": run.calls,
        "tokens": run.tokens,
        "steps": run.steps,
    }
