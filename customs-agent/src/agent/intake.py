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


OVER_21 = re.compile(
    r"\b(?:over|above|older than|at least|past)\s+(?:the age of\s+)?21\b|\b21\s*\+|\b21 or (?:over|older|above)\b|"
    r"\b(?:of )?legal (?:drinking )?age\b",
    re.IGNORECASE,
)


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
    if OVER_21.search(question or "") and (
        p.age is None or str(p.age) not in numbers_in_q
    ):
        # "over 21", "21+", "of legal drinking age": the rules only need "not under 21"
        upd["age"] = 21
        dropped.append("age: stated as 21 or over")
    elif p.age is not None and str(p.age) not in numbers_in_q:
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


ABV_STATED = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:%|percent|per cent|abv\b|% abv)|(\d+(?:\.\d+)?)\s*proof\b|\babv\s*(?:of\s*)?(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def abvs_in(text: str) -> set[float]:
    out: set[float] = set()
    for m in ABV_STATED.finditer(text or ""):
        if m.group(1):
            out.add(float(m.group(1)))
        elif m.group(2):
            out.add(float(m.group(2)) / 2)  # US proof = 2 x ABV
        elif m.group(3):
            out.add(float(m.group(3)))
    return out


def countries_in(text: str) -> set[str]:
    """ISO codes of countries named in a text (names, demonyms; not 2-letter words like "in")."""
    words = re.findall(r"[A-Za-zÀ-ÿ'.]+", text or "")  # "Cuban-made" -> "Cuban", "made"
    out: set[str] = set()
    for n in (3, 2, 1):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i : i + n]).strip(".'")
            if len(phrase) <= 2:
                continue
            code = to_iso2(phrase)
            if code:
                out.add(code)
    return out


def _risk_line(b: BasketLine) -> bool:
    """Items whose origin could make them banned or sanctioned (rules.yaml ask_origin_when)."""
    from src.tools.common import rules

    name = (b.item or "").lower()
    for rule in rules()["restrictions"]:
        ask = rule.get("ask_origin_when") or {}
        if b.type in ask.get("types", []) or any(
            k in name for k in ask.get("item_keywords", [])
        ):
            return True
    return False


EXPORT_LABEL = re.compile(
    r"\b(?:for export|export(?:ed)?[- ]label\w*|label+ed for export|tax[- ]exempt for export|"
    r"not for sale in the (?:us|u\.s\.|united states)|us[- ]made|u\.s\.[- ]made|"
    r"made in (?:the )?(?:usa|us|u\.s\.|united states|america)|american[- ](?:made|brand)\w*|american cigarettes)\b",
    re.IGNORECASE,
)
AMERICAN_RETURNED = re.compile(
    r"\b(?:american goods returned|us goods returned|made in (?:the )?(?:usa|us|u\.s\.|united states)|"
    r"(?:bought|purchased) (?:it|them|these) in the (?:us|u\.s\.|states)|originally (?:from|bought in) the (?:us|u\.s\.|states))\b",
    re.IGNORECASE,
)
FLAGS = {
    "export_labelled_us": EXPORT_LABEL,
    "claims_american_goods_returned": AMERICAN_RETURNED,
}


def ground_items(
    r: IntakeResult, question: str, only: dict[int, set[str]] | None = None
) -> tuple[IntakeResult, list[str]]:
    """Drop item facts the question does not state: an ABV with no matching "40%" / "80 proof",
    the origin of an item that could be Cuban or Russian when no country is named (a guessed
    origin would hide the question SPEC 5.2 requires), and the export-label / American-goods
    flags unless the question says so (each switches on a different rule). `only`: {line index: fields} to check (a
    later turn checks only the facts its message changed)."""
    abvs, named = abvs_in(question), countries_in(question)
    notes: list[str] = []
    basket = list(r.basket)
    for i, b in enumerate(basket):
        fields = {"abv", "origin", *FLAGS} if only is None else only.get(i, set())
        upd: dict[str, Any] = {}
        if (
            "abv" in fields
            and b.abv is not None
            and not any(abs(b.abv - a) < 0.051 for a in abvs)
        ):
            upd["abv"] = None
            notes.append(f"item {i + 1} abv {b.abv:g} dropped (not in the question)")
        if "origin" in fields and b.origin and _risk_line(b) and b.origin not in named:
            upd["origin"] = None
            notes.append(
                f"item {i + 1} origin {b.origin} dropped (no country named for it)"
            )
        for (
            flag,
            pattern,
        ) in FLAGS.items():  # special rules switch on these: never on a guess
            if (
                flag in fields
                and getattr(b, flag)
                and not pattern.search(question or "")
            ):
                upd[flag] = False
                notes.append(
                    f"item {i + 1} {flag} dropped (not stated in the question)"
                )
        if upd:
            basket[i] = b.model_copy(update=upd)
    if not notes:
        return r, []
    return r.model_copy(update={"basket": basket}), notes


NOT_USED = re.compile(
    r"\b(?:first (?:\w+ )?(?:trip|time|travel|holiday|vacation)\w*|no (?:other |previous |earlier )?(?:trips?|travel)|"
    r"(?:haven'?t|have not|hasn'?t|has not|never) (?:\w+ )?(?:used (?:my|the|it)|been abroad|travel+ed|been away)|"
    r"not (?:used|been abroad)|in (?:months|a year|years|ages))\b",
    re.IGNORECASE,
)


def history_from_question(
    r: IntakeResult, question: str
) -> tuple[IntakeResult, list[str]]:
    """'first trip this year', 'no other trips', 'haven't used my exemption': not used in the last
    30 days, set in code when the model left it empty (the intake prompt asks the same)."""
    p = r.profile
    if p.exemption_used_last_30_days is not None or not NOT_USED.search(question or ""):
        return r, []
    return (
        r.model_copy(
            update={
                "profile": p.model_copy(update={"exemption_used_last_30_days": False})
            }
        ),
        ["exemption_used_last_30_days: not used (stated in the question)"],
    )
