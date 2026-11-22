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
from src.schemas import Amount, BasketLine, Profile


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


HISTORY = re.compile(
    r"\b(first (?:\w+ )?(?:trip|time|travel|holiday|vacation)\w*|no (?:other |previous |earlier )?(?:trips?|travel)|"
    r"(?:haven'?t|have not|hasn'?t|has not|not|never) (?:\w+ )?(?:used|been|travel+ed|gone|left)|"
    r"exemptions?|allowances?|(?:trips?|abroad|away|travel+ed) (?:this|last|in the (?:last|past)) (?:year|month|30 days)|"
    r"in (?:months|a year|years|ages)|last 30 days|past month|earlier this month|(?:another|other|previous) trip)\b",
    re.IGNORECASE,
)


_UNITS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
SPELLED = re.compile(
    rf"\b(?:(?P<tens>{'|'.join(_TENS)})(?:[\s-]+(?P<unit>{'|'.join(_UNITS[1:10])}))?|(?P<small>{'|'.join(_UNITS)}))\b",
    re.IGNORECASE,
)


def spelled_numbers(text: str) -> set[str]:
    """Numbers written in words, 0-99 ("forty-nine", "twenty one", "seventeen"), as digit strings."""
    out = set()
    for m in SPELLED.finditer(text):
        if m.group("tens"):
            n = 20 + 10 * _TENS.index(m.group("tens").lower())
            if m.group("unit"):
                n += _UNITS.index(m.group("unit").lower())
        else:
            n = _UNITS.index(m.group("small").lower())
        out.add(str(n))
    return out


def ground_in_question(
    r: IntakeResult, question: str
) -> tuple[IntakeResult, list[str]]:
    """Drop profile facts the question does not state (the model fills gaps with guesses).

    Age must appear as a number in the question, in digits or words ("49", "forty-nine"); a trip length needs some duration in it
    ("10 days", "a week", "day trip", "overnight"); the 30-day history needs something about earlier
    trips or the exemption ("first trip this year", "haven't used my exemption"). Anything dropped
    becomes null, so the clarify
    policy asks for it (SPEC 5.2) instead of answering on a guess.
    """
    dropped: list[str] = []
    upd: dict[str, Any] = {}
    numbers_in_q = set(re.findall(r"\d+", question or "")) | spelled_numbers(
        question or ""
    )
    p = r.profile
    if p.age is not None and str(p.age) not in numbers_in_q:
        upd["age"] = None
        dropped.append(f"age {p.age} (not in the question)")
    if p.trip is not None and not DURATION.search(question or ""):
        upd["trip"] = None
        dropped.append(
            f"trip {p.trip.value:g} {p.trip.unit} (no duration in the question)"
        )
    for name in ("exemption_used_last_30_days", "flat_rate_used_last_30_days"):
        if getattr(p, name, None) is not None and not HISTORY.search(question or ""):
            upd[name] = None
            dropped.append(f"{name} (nothing about earlier trips in the question)")
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


SIZE = re.compile(
    r"(\d+(?:\.\d+)?)\s*-?\s*(ml|millilit(?:re|er)s?|cl|centilit(?:re|er)s?|l|lit(?:re|er)s?|fl\.? ?oz)\b",
    re.IGNORECASE,
)
SIZE_WORDS = re.compile(
    r"\b(fifths?|magnums?|half[- ]bottles?|splits?|miniatures?|minis|nips?|a lit(?:re|er)|one lit(?:re|er)|lit(?:re|er)[- ]bottles?)\b",
    re.IGNORECASE,
)
_UNIT = {
    "millilitre": "ml",
    "milliliter": "ml",
    "centilitre": "cl",
    "centiliter": "cl",
    "liter": "litre",
}


def _unit_word(u: str) -> str:
    u = u.lower().replace(".", "")
    u = u[:-1] if u.endswith("s") and u not in ("fl oz",) else u
    u = _UNIT.get(u, u)
    return "fl oz" if u.replace(" ", "") == "floz" else u


def sizes_from_question(
    r: IntakeResult, question: str
) -> tuple[IntakeResult, list[str]]:
    """Container sizes: read from the question in code when intake misses them ("75cl"), and dropped
    when the question states none (no invented "1 litre"). Lines are paired with sizes in order."""
    q = question or ""
    stated = [
        {"value": float(m.group(1)), "unit": _unit_word(m.group(2))}
        for m in SIZE.finditer(q)
    ]
    any_size = bool(stated) or bool(SIZE_WORDS.search(q))
    alcohol = [i for i, b in enumerate(r.basket) if b.category == "alcohol"]
    changes: list[str] = []
    basket = list(r.basket)
    if not any_size:
        for i in alcohol:
            if basket[i].size is not None:
                sz = basket[i].size
                changes.append(
                    f"item {i + 1} size {sz.value:g} {sz.unit} dropped (no size in the question)"
                )
                basket[i] = basket[i].model_copy(update={"size": None})
    else:
        lacking = [i for i in alcohol if basket[i].size is None]
        distinct = {(x["value"], x["unit"]) for x in stated}
        pairs: list[tuple[int, dict]] = []
        if lacking and stated:
            if len(distinct) == 1:
                pairs = [(i, stated[0]) for i in lacking]
            elif len(stated) == len(alcohol):
                pairs = [(i, stated[alcohol.index(i)]) for i in lacking]
        for i, sz in pairs:
            changes.append(
                f"item {i + 1} size {sz['value']:g} {sz['unit']} read from the question"
            )
            basket[i] = basket[i].model_copy(update={"size": Amount(**sz)})
    if not changes:
        return r, []
    return r.model_copy(update={"basket": basket}), changes
