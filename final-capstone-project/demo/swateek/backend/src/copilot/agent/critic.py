"""The critic: deterministic checks first, then an LLM review (Track B: explicit critic role).

Deterministic (always, no model call):
  - every [P#] ref in the draft was actually retrieved in this run
  - after a search, every factual sentence carries a ref
  - a matched refusal rule is actually declined
  - no banned phrase for the jobs the run touched (domain refusals.yaml)
  - the domain's own checks (domains/<name>/critic_rules.py: check(draft, payloads) -> problems)
LLM review (only if the deterministic checks pass and a step is left): is every cited sentence
supported by the cited text? Verdict is strict JSON (constrained decoding).
"""

from __future__ import annotations

import importlib.util
import json
import re
from typing import Any

from pydantic import BaseModel, Field

from copilot.agent.context import BudgetExceeded, require
from copilot.agent.refusals import RefusalPolicy
from copilot.domains.loader import DomainConfig

REF = re.compile(r"\[(P\d+)\]")
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")
DECLINE = re.compile(
    r"\b(can(?:'|no)t|cannot|unable to|not able to|won't|will not|decline|do not|don't|"
    r"not (?:in|part of) the indexed|competent authority)\b",
    re.IGNORECASE,
)
EXEMPT = re.compile(
    r"\b(draft|not an award|not a finding|competent authority|cannot find|can't find|"
    r"decline|cannot|can't|I can)\b",
    re.IGNORECASE,
)


class LLMVerdict(BaseModel):
    supported: bool
    problems: list[str] = Field(default_factory=list, max_length=4)


class Critic:
    def __init__(self, domain: DomainConfig, policy: RefusalPolicy, llm: Any, prompt: str) -> None:
        self.domain = domain
        self.policy = policy
        self.llm = llm
        self.prompt = prompt
        self.domain_check = _load_domain_check(domain)
        self.mode_of_tool = {}  # tool name -> ui mode, filled by the harness

    def deterministic(self, draft: str) -> list[str]:
        ctx = require()
        problems: list[str] = []
        used = REF.findall(draft)
        unknown = sorted({r for r in used if r not in ctx.refs})
        if unknown:
            problems.append(
                f"Cites refs that were never retrieved: {', '.join(unknown)}. "
                "Cite only refs from the search results."
            )
        searched = any(p["tool"] in self.search_tools for p in ctx.tool_payloads)
        if searched and not ctx.refusal_hits:
            uncited = [
                s
                for s in SENTENCE.split(draft.strip())
                if len(s.split()) >= 6 and not REF.search(s) and not EXEMPT.search(s)
            ]
            if uncited:
                problems.append(
                    "These sentences state facts without a [P#] ref: "
                    + " | ".join(u[:120] for u in uncited[:3])
                )
        if not ctx.tool_payloads and not ctx.refusal_hits and len(draft.split()) > 30:
            problems.append(
                "This answer states facts without using any tool. Delegate to the executor so "
                "the answer comes from the indexed rules, the screening lists or the score sheet."
            )
        for hit in ctx.refusal_hits:
            if not DECLINE.search(draft):
                problems.append(
                    f"The request matches refusal rule {hit.rule_id}; the answer "
                    f"must decline and say why: {hit.wording}"
                )
        jobs = sorted({self.mode_of_tool.get(p["tool"], "") for p in ctx.tool_payloads} - {""})
        banned = self.policy.banned_in(draft, jobs)
        if banned:
            problems.append(f"Uses wording that is not allowed: {', '.join(banned)}.")
        if self.domain_check:
            problems += self.domain_check(draft, ctx.tool_payloads)
        return problems

    def llm_review(self, question: str, draft: str) -> list[str]:
        ctx = require()
        cited = sorted(set(REF.findall(draft)), key=lambda r: int(r[1:]))
        if not cited:
            return []
        try:
            ctx.take_step()
        except BudgetExceeded:
            ctx.emit("critic_skipped", reason="no step left for the LLM review")
            return []
        sources = "\n\n".join(
            f"[{r}] {ctx.refs[r]['title']}\n{ctx.refs[r]['text'][:1500]}"
            for r in cited
            if r in ctx.refs
        )
        messages = [
            ("system", self.prompt),
            (
                "human",
                f"Question: {question}\n\nDraft answer:\n{draft}\n\nCited sources:\n{sources}",
            ),
        ]
        try:
            result = self.llm.with_structured_output(
                LLMVerdict, method="json_schema", strict=True, include_raw=True
            ).invoke(messages)
        except Exception as err:  # noqa: BLE001 - a failed review is recorded, not fatal
            ctx.emit("critic_error", error=f"{type(err).__name__}: {err}"[:200])
            return []
        raw = result.get("raw")
        usage = getattr(raw, "usage_metadata", None) or {}
        ctx.add_tokens(int(usage.get("total_tokens", 0) or 0))
        verdict = result.get("parsed")
        if verdict is None:  # malformed JSON despite constrained decoding: record, don't block
            ctx.emit("critic_error", error=str(result.get("parsing_error"))[:200])
            return []
        return (
            []
            if verdict.supported
            else [f"Not supported by the cited text: {p}" for p in verdict.problems]
            or ["A cited sentence is not supported by its source."]
        )

    def review(self, question: str, draft: str) -> dict[str, Any]:
        problems = self.deterministic(draft)
        llm_problems: list[str] = []
        if not problems:
            llm_problems = self.llm_review(question, draft)
        # Only deterministic problems block. The 8B critic rejected correct, cited answers in
        # testing (small-model-log #15), so its notes are advisory: recorded and shown, not fatal.
        return {
            "passed": not problems,
            "problems": problems,
            "deterministic": problems,
            "llm": llm_problems,
        }

    @property
    def search_tools(self) -> set[str]:
        return {name for name, mode in self.mode_of_tool.items() if mode == "__search__"}


def _load_domain_check(domain: DomainConfig):
    path = domain.path("critic_rules.py")
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"domain_{domain.name}_critic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "check", None)


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)
