"""lookup_state_rule: the arrival-state flag (rules.yaml -> flags). Note and source only; no amounts.

STATE_RULES=spec (default): the five states of SPEC 5.4, as the frozen eval gold expects; the
official runs use this. STATE_RULES=all: those five plus the ten `extended_states` (stretch,
Day 9); the web app sets it.
"""

from __future__ import annotations

import os

from pydantic import BaseModel

from src.schemas import StateFlag
from src.tools.common import rules

MODES = ("spec", "all")


class Args(BaseModel):
    arrival_state: str | None


def state_rules_mode() -> str:
    mode = os.environ.get("STATE_RULES", "spec").strip().lower()
    if mode not in MODES:
        raise ValueError(f"STATE_RULES must be one of {MODES}, not {mode!r}")
    return mode


def covered_states() -> dict[str, dict]:
    flags = rules()["flags"]["state_alcohol_limits"]
    states = dict(flags["states"])
    if state_rules_mode() == "all":
        states.update(flags.get("extended_states") or {})
    return states


def lookup_state_rule(args: Args) -> StateFlag | None:
    flags = rules()["flags"]["state_alcohol_limits"]
    st = (args.arrival_state or "").upper()
    s = covered_states().get(st)
    if s is None:
        return None
    return StateFlag(
        state=st,
        name=s["name"],
        note=s["note"],
        source=s["source"],
        general_note=flags["general_note"],
        citations=flags.get("citations", []),
    )
