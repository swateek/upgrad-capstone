"""Intake (plan §4.1): one strict-JSON model call turns the message into profile + basket.

On a clarify reply or a correction the model sees the current facts and returns them updated;
code then works out the field delta and which steps it makes stale (plan §4.5 dependency map).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from customs.agent.context import current
from customs.config import PROJECT_ROOT
from customs.llm.chat import ChatClient
from customs.tools.models import Line, Profile

PROMPT = PROJECT_ROOT / "pack" / "prompts" / "agent_intake.md"
MAX_TOKENS = 700

# fact -> the steps whose results it changes (plan §4.5)
DEPENDS = {
    "age": ["check_restrictions", "compute_allowance", "compute_duty_excise"],
    "trip_hours": ["determine_exemption", "compute_allowance", "compute_duty_excise"],
    "exemption_used_last_30_days": ["determine_exemption", "compute_allowance", "compute_duty_excise"],
    "arrived_directly_from": ["check_restrictions", "determine_exemption", "compute_allowance",
                              "compute_duty_excise"],
    "arrival_state": ["lookup_state_rule"],
    "us_resident": ["check_restrictions"],
}  # fmt: skip
LINE_STEPS = ["check_restrictions", "compute_allowance", "compute_duty_excise"]


class Facts(BaseModel):
    model_config = ConfigDict(extra="ignore")
    profile: Profile
    basket: list[Line]


def user_content(message: str, facts: dict | None, asked: str | None) -> str:
    parts = []
    if facts:
        parts.append(f"CURRENT FACTS: {json.dumps(facts, separators=(',', ':'))}")
    if asked:
        parts.append(f"You asked the traveller: {asked}")
    parts.append(f"Traveller: {message}")
    return "\n\n".join(parts)


def run_intake(chat: ChatClient, message: str, facts: dict | None, asked: str | None) -> Facts:
    msgs = [
        {"role": "system", "content": PROMPT.read_text(encoding="utf-8").strip()},
        {"role": "user", "content": user_content(message, facts, asked)},
    ]
    ctx = current()
    ctx.before_model_call()
    res = chat.complete(msgs, max_tokens=MAX_TOKENS, response_model=Facts, name="intake")
    ctx.after_model_call("intake", res)
    return res.parsed


def dump(f: Facts) -> dict[str, Any]:
    return {
        "profile": f.profile.model_dump(exclude_defaults=True),
        "basket": [ln.model_dump(exclude_none=True) for ln in f.basket],
    }


def delta(old: dict | None, new: dict) -> list[str]:
    """Changed fact names: profile fields, and 'line N' for changed, added or removed lines."""
    if not old:
        return []
    out = []
    op, np_ = old.get("profile", {}), new.get("profile", {})
    for k in sorted(set(op) | set(np_)):
        if op.get(k) != np_.get(k):
            out.append(k)
    ob, nb = old.get("basket", []), new.get("basket", [])
    for i in range(max(len(ob), len(nb))):
        if (ob[i] if i < len(ob) else None) != (nb[i] if i < len(nb) else None):
            out.append(f"line {i + 1}")
    return out


def stale_steps(changed: list[str]) -> list[str]:
    steps: list[str] = []
    for c in changed:
        for s in LINE_STEPS if c.startswith("line ") else DEPENDS.get(c, []):
            if s not in steps:
                steps.append(s)
    return steps
