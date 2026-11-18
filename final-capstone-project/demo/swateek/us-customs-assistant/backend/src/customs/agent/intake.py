"""Intake (plan §4.1): one strict-JSON model call turns the message into profile + basket.

On a clarify reply or a correction the model sees the current facts and returns them updated;
code then works out the field delta and which steps it makes stale (plan §4.5 dependency map).
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from customs.agent.context import current
from customs.config import PROJECT_ROOT
from customs.llm.chat import ChatClient
from customs.tools.models import Line, Profile
from customs.tools.tables import Tables

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


class IntakeProfile(BaseModel):
    """What the model fills (SPEC §3 profile, reshaped for a small model; converted in code).

    - trip_hours is a number only; the 48-hour bucket is a separate yes/no used only when no
      length is given (dev run 1: a "<48" string option was chosen for a 6-day trip).
    - us_resident / crew / shipped need `scope_quote`, the traveller's own words; code drops
      the flag when the quote is not in the conversation (dev run 1: "back from Dublin" was
      read as non-resident).
    """

    model_config = ConfigDict(extra="ignore")
    age: int | None = None
    trip_hours: float | None = None
    trip_at_least_48_hours: bool | None = None
    arrived_directly_from: str | None = None
    countries_visited: list[str] = Field(default_factory=list)
    exemption_used_last_30_days: bool | None = None
    arrival_state: str | None = None
    us_resident: bool = True
    travelling_as_family: bool = False
    crew: bool = False
    shipped: bool = False
    scope_quote: str | None = None


class Facts(BaseModel):
    model_config = ConfigDict(extra="ignore")
    profile: IntakeProfile
    basket: list[Line]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def to_profile(ip: IntakeProfile, conversation: str) -> tuple[Profile, list[str]]:
    """The SPEC profile from the intake's, and the scope flags dropped for lack of evidence."""
    d = ip.model_dump(exclude={"trip_at_least_48_hours", "scope_quote"})
    if ip.trip_hours is None and ip.trip_at_least_48_hours is not None:
        d["trip_hours"] = ">=48" if ip.trip_at_least_48_hours else "<48"
    quote = _norm(ip.scope_quote or "")
    grounded = bool(quote) and quote in _norm(conversation)
    dropped = []
    for flag, normal in (("us_resident", True), ("crew", False), ("shipped", False)):
        if d[flag] != normal and not grounded:
            d[flag] = normal
            dropped.append(flag)
    return Profile.model_validate(d), dropped


US_STATES = frozenset(
    [
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
        "PR",
    ]
)
CUBA_CUE = re.compile(r"\b(cuba|cuban)\b|\bhavana\b(?!\s+club)", re.IGNORECASE)
CIGAR = re.compile(r"\bcigars?\b", re.IGNORECASE)
CIGARETTE = re.compile(r"\bcigarettes?\b|\bcartons?\b|\bpacks?\b", re.IGNORECASE)
BRAND_ITEMS = {"cigars": {"cigars"}, "rum": {"spirits", "liqueur"}}


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()


def ground(facts: dict, conversation: str, tables: Tables) -> list[str]:
    """Code checks on facts that decide sanctions and flags (dev run 2: the model read
    "Havana Club" as made in Cuba, dropped the brand, and gave "ON" as the arrival state).
    Mutates `facts`; returns what it changed, for the trace."""
    fixes = []
    conv = _fold(conversation)
    prof = facts["profile"]
    visited = prof.get("countries_visited") or []
    if not prof.get("arrived_directly_from") and len(set(visited)) == 1:
        # a one-country trip comes back from that country (live smoke test 18 Nov: "Tijuana,
        # Mexico, driving straight back" gave countries_visited [MX] and no arrival country,
        # so a land crossing from Mexico was asked about again)
        prof["arrived_directly_from"] = visited[0]
        fixes.append(f"arrived_directly_from {visited[0]} (the only country visited)")
    st = prof.get("arrival_state")
    if st and str(st).upper() not in US_STATES:
        prof.pop("arrival_state")
        fixes.append(f"arrival_state {st!r} is not a US state")
    for group, brands in tables.brands["ambiguous_brands"].items():
        for b in brands:
            if _fold(b) in conv:
                for i, ln in enumerate(facts["basket"], start=1):
                    if ln.get("item") in BRAND_ITEMS.get(group, set()) and not ln.get("brand"):
                        ln["brand"] = b
                        fixes.append(f"line {i}: brand {b} (named by the traveller)")
    cigar_words = bool(CIGAR.search(conversation))
    cigarette_words = bool(CIGARETTE.search(conversation))
    for i, ln in enumerate(facts["basket"], start=1):
        if str(ln.get("origin") or "").upper() == "CU" and not CUBA_CUE.search(conversation):
            ln.pop("origin")
            fixes.append(f"line {i}: origin CU dropped (Cuba never mentioned)")
        # dev run 3: "10 cigars" came back as cigarettes
        if ln.get("item") == "cigarettes" and cigar_words and not cigarette_words:
            ln["item"] = "cigars"
            fixes.append(f"line {i}: cigarettes -> cigars (the traveller said cigars)")
        elif ln.get("item") == "cigars" and cigarette_words and not cigar_words:
            ln["item"] = "cigarettes"
            fixes.append(f"line {i}: cigars -> cigarettes (the traveller said cigarettes)")
        # dev run 3: "a 50 ml bottle" came back as quantity 1, unit ml (1 ml)
        unit, q, size = (
            str(ln.get("unit") or "").lower(),
            ln.get("quantity"),
            ln.get("container_ml"),
        )
        per_ml = {"ml": 1, "l": 1000}.get(unit)
        if per_ml and q and size and q * per_ml < size:
            ln["unit"] = "bottle"
            fixes.append(f"line {i}: {q:g} {unit} is less than one {size:g} ml container; "
                         f"read as {q:g} container(s)")  # fmt: skip
    return fixes


SAME_LINE = ("item", "quantity", "unit", "container_ml", "brand")


def merge_reply_lines(old: dict, new: dict) -> list[str]:
    """On a reply to a facts-only clarifying question, a 'new' line that repeats an existing
    line (same item, quantity, unit, size, brand) is that line with the asked fact filled in
    (dev run 4: "It says Puerto Rico on the label" came back as a second rum bottle).
    Mutates `new`; returns what it merged."""
    ob, nb = old.get("basket", []), new.get("basket", [])
    merged = []
    for i in range(len(nb) - 1, len(ob) - 1, -1):
        extra = nb[i]
        for j in range(len(ob)):
            if all(extra.get(k) == nb[j].get(k) for k in SAME_LINE):
                nb[j] = nb[j] | {k: v for k, v in extra.items() if v is not None}
                del nb[i]
                merged.append(f"line {i + 1} merged into line {j + 1}")
                break
    return merged


def to_intake(profile: dict) -> dict:
    """CURRENT FACTS for the model, in its own shape."""
    d = dict(profile)
    th = d.get("trip_hours")
    if isinstance(th, str):
        d.pop("trip_hours")
        d["trip_at_least_48_hours"] = th == ">=48"
    return d


def user_content(message: str, facts: dict | None, asked: str | None) -> str:
    parts = []
    if facts:
        shown = {"profile": to_intake(facts.get("profile", {})), "basket": facts.get("basket", [])}
        parts.append(f"CURRENT FACTS: {json.dumps(shown, separators=(',', ':'))}")
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


def dump(f: Facts, conversation: str) -> tuple[dict[str, Any], list[str]]:
    """Facts as kept in state (SPEC shapes), and any scope flag dropped for lack of evidence."""
    profile, dropped = to_profile(f.profile, conversation)
    return {
        "profile": profile.model_dump(exclude_defaults=True),
        "basket": [ln.model_dump(exclude_none=True) for ln in f.basket],
    }, dropped


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
