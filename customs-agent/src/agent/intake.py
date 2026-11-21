"""Intake: one LLM call turns the question into a profile and a basket (JSON), as stated.

Code converts units later (normalise_units); the model never converts or computes.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, model_validator

from src.agent import prompts
from src.agent.countries import ALIASES, to_iso2
from src.agent.llm_json import Usage, json_call
from src.baselines.answer import Strict
from src.schemas import BasketLine, Profile


class IntakeResult(Strict):
    request_kind: Literal["assess", "evasion", "injection", "out_of_scope"]
    profile: Profile
    basket: list[BasketLine] = Field(default_factory=list)
    owe_less_than_usd: float | None = Field(
        None, gt=0, description="What-if target: owe less than this many dollars"
    )

    @model_validator(mode="before")
    @classmethod
    def zero_means_unknown(cls, data: Any) -> Any:
        """Small models write 0 for "not stated": treat it as null (COMPENSATIONS row 3 family).

        A line with no quantity is not an item, except in a what-if question, where the quantity is
        what we are solving for (set to 1; whatif_optimise varies it).
        """
        if not isinstance(data, dict):
            return data
        whatif = (data.get("owe_less_than_usd") or 0) > 0
        if not whatif:
            data["owe_less_than_usd"] = None
        prof = data.get("profile") or {}
        if (
            isinstance(prof.get("trip"), dict)
            and not (prof["trip"].get("value") or 0) > 0
        ):
            prof["trip"] = None
        if isinstance(prof.get("age"), (int, float)) and prof["age"] <= 0:
            prof["age"] = None
        basket = []
        for ln in data.get("basket") or []:
            if not isinstance(ln, dict):
                continue
            q = ln.get("quantity") if isinstance(ln.get("quantity"), dict) else {}
            if not (q.get("value") or 0) > 0:
                if not whatif:
                    continue
                ln["quantity"] = {"value": 1, "unit": q.get("unit") or "bottle"}
            if (
                isinstance(ln.get("size"), dict)
                and not (ln["size"].get("value") or 0) > 0
            ):
                ln["size"] = None
            if ln.get("abv") is not None and ln["abv"] <= 0:
                ln["abv"] = None
            if ln.get("unit_price_usd") is not None and ln["unit_price_usd"] < 0:
                ln["unit_price_usd"] = None
            basket.append(ln)
        data["basket"] = basket
        return data


def extract(llm: Any, usage: Usage, question: str) -> IntakeResult:
    return json_call(
        llm,
        usage,
        IntakeResult,
        [
            {"role": "system", "content": prompts.INTAKE},
            {"role": "user", "content": question},
        ],
        stage="intake",
        max_tokens=700,
    )


def normalise_countries(r: IntakeResult) -> tuple[IntakeResult, list[str]]:
    """Country names and demonyms -> ISO codes, in code. Unrecognised origins become null, so the
    clarify policy asks for them when they matter. Returns the changes made, for the trace."""
    changes: list[str] = []

    def fix(field: str, value: str | None, keep_text: bool = False) -> str | None:
        if value is None:
            return None
        code = to_iso2(value)
        if code != value:
            changes.append(
                f"{field}: {value!r} -> {code!r}"
                if code or not keep_text
                else f"{field}: {value!r} kept"
            )
        return code if code or not keep_text else value

    profile = r.profile.model_copy(
        update={
            "direct_arrival_from": fix(
                "direct_arrival_from", r.profile.direct_arrival_from
            )
        }
    )
    basket = [
        b.model_copy(
            update={
                "origin": fix(f"item {i} origin", b.origin),
                "bought_where": fix(
                    f"item {i} bought_where", b.bought_where, keep_text=True
                ),
            }
        )
        for i, b in enumerate(r.basket, start=1)
    ]
    return r.model_copy(update={"profile": profile, "basket": basket}), [
        c for c in changes if not c.endswith("kept")
    ]


NUMBER_WORDS = r"\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|a couple of|a few|several"
DURATION = re.compile(
    rf"\b(?:{NUMBER_WORDS})[\s-]*(?:hours?|hrs?|days?|nights?|weeks?|wks?|months?|fortnight)\b"
    r"|\bday[\s-]?trip\b|\bovernight\b|\bweekend\b|\bfortnight\b|\bsame[\s-]day\b|\bfor the day\b",
    re.IGNORECASE,
)


def ground_in_question(
    r: IntakeResult, question: str
) -> tuple[IntakeResult, list[str]]:
    """Drop profile facts the question does not state (the model fills gaps with guesses).

    Age must appear as a number in the question; a trip length needs some duration in it
    ("10 days", "a week", "day trip", "overnight"). Anything dropped becomes null, so the clarify
    policy asks for it (SPEC 5.2) instead of answering on a guess.
    """
    dropped: list[str] = []
    upd: dict[str, Any] = {}
    numbers_in_q = set(re.findall(r"\d+", question or ""))
    p = r.profile
    if p.age is not None and str(p.age) not in numbers_in_q:
        upd["age"] = None
        dropped.append(f"age {p.age} (not in the question)")
    if p.trip is not None and not DURATION.search(question or ""):
        upd["trip"] = None
        dropped.append(
            f"trip {p.trip.value:g} {p.trip.unit} (no duration in the question)"
        )
    if not upd:
        return r, []
    return r.model_copy(update={"profile": p.model_copy(update=upd)}), dropped


PRODUCT_WORDS = {
    "wine": r"wines?|reds?|whites?|ros[eé]|champagnes?|proseccos?|cavas?|ports?|sherr(?:y|ies)|sakes?|madeiras?",
    "sparkling_wine": r"wines?|champagnes?|proseccos?|cavas?|sparkling",
    "spirits": r"vodkas?|rums?|gins?|whisk(?:e)?ys?|whiskies|scotch|bourbons?|tequilas?|mezcals?|brand(?:y|ies)|cognacs?|liqueurs?|grappas?|sojus?|spirits?|piscos?|cacha[cç]as?",
    "beer": r"beers?|ales?|lagers?|stouts?|ciders?",
    "cigars": r"cigars?|habanos?",
    "cigarettes": r"cigarettes?",
}
_COUNTRY_WORDS = sorted(
    {k for k in ALIASES if re.fullmatch(r"[a-z ]+", k)}, key=len, reverse=True
)
_NATION = "|".join(re.escape(k) for k in _COUNTRY_WORDS)


def origin_from_question(
    r: IntakeResult, question: str
) -> tuple[IntakeResult, list[str]]:
    """Origin stated with the product in the question ("Cuban cigars", "Polish vodka") wins over the
    model's origin. The model sometimes writes where it was bought instead ("Cuban cigars bought in
    Cancún" -> MX), which would miss the Cuban ban. Lines are matched by product type, in order."""
    changes: list[str] = []
    basket = list(r.basket)
    for ptype, words in PRODUCT_WORDS.items():
        idx = [i for i, b in enumerate(basket) if b.type == ptype]
        if not idx:
            continue
        pat = re.compile(
            rf"\b({_NATION})\s+(?:[a-z-]+\s+){{0,2}}?(?:{words})\b", re.IGNORECASE
        )
        found = [to_iso2(m.group(1)) for m in pat.finditer(question or "")]
        found = [c for c in found if c]
        if not found or len(found) != len(idx):
            continue  # cannot pair stated origins with lines safely
        for i, code in zip(idx, found, strict=True):
            if basket[i].origin != code:
                changes.append(
                    f"item {i + 1} origin {basket[i].origin!r} -> {code!r} (stated in the question)"
                )
                basket[i] = basket[i].model_copy(update={"origin": code})
    if not changes:
        return r, []
    return r.model_copy(update={"basket": basket}), changes
