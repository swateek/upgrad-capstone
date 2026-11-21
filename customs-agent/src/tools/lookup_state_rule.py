"""lookup_state_rule: the arrival-state flag (five states, rules.yaml -> flags). Note and source only; no amounts."""

from __future__ import annotations

from pydantic import BaseModel

from src.schemas import StateFlag
from src.tools.common import rules


class Args(BaseModel):
    arrival_state: str | None


def lookup_state_rule(args: Args) -> StateFlag | None:
    flags = rules()["flags"]["state_alcohol_limits"]
    st = (args.arrival_state or "").upper()
    if st not in flags["states"]:
        return None
    s = flags["states"][st]
    return StateFlag(
        state=st,
        name=s["name"],
        note=s["note"],
        source=s["source"],
        general_note=flags["general_note"],
        citations=flags.get("citations", []),
    )
