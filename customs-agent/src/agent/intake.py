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


# Phrases that say the exemption was NOT used in the last 30 days ("first trip this year",
# "hadn't been abroad for months", "my only trip in the last few months", "last trip was 8 months
# ago"). Shared by HISTORY (keep the model's history value) and history_from_question (set it).
_NEG = r"(?:haven'?t|have not|hasn'?t|has not|hadn'?t|had not|never|didn'?t|did not)"
_NOT_USED = (
    r"first (?:\w+ )?(?:trip|time|travel|holiday|vacation)\w*|"
    r"only (?:\w+ )?(?:trip|time|travel|holiday|vacation)\w*|"
    r"no (?:other |previous |earlier |recent |prior )?(?:international |overseas |foreign |abroad )?(?:trips?|travel)|"
    rf"{_NEG} (?:\w+ ){{0,2}}?(?:used (?:my|the|it|any|an?)|claimed|been (?:abroad|away|overseas|out of the (?:country|us|u\.s\.))|"
    r"travel+ed|left the (?:country|us|u\.s\.|states)|gone (?:abroad|overseas)|crossed the border|"
    r"(?:gone|been|travel+ed|went) anywhere)|"
    r"not (?:used|claimed|been abroad)|in (?:months|a year|years|ages|a while|a long time|over a year)|"
    r"(?:last|previous|prior) (?:\w+ ){0,5}?(?:\d+|a|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|several|a few|many) (?:months|years) ago|"
    # agent v2 (dev-v2): gaps and firsts
    r"(?:last|previous|prior) (?:\w+ ){0,4}?(?:was|went abroad|travel+ed) (?:\w+ ){0,2}?(?:over|more than) a year ago|"
    r"(?:been|it'?s been) (?:more than |over |about |almost |nearly )?(?:a|one|two|three|\d+) (?:years?|months) since|"
    r"(?:no|nothing|zero) (?:\w+ ){0,3}?(?:in|for) (?:the (?:last|past) )?(?:\d+|two|three|four|five|several|a few|many) (?:years|months)|"
    r"(?:no|nothing|zero) (?:\w+ ){0,3}?(?:all|this) year|"
    r"first (?:passport stamp|customs (?:claim|declaration)|time (?:abroad|overseas|out of the country))|"
    r"stayed (?:in the (?:us|u\.s\.|states|country)|home) (?:all year|the whole year|until this trip)"
)
HISTORY = re.compile(
    rf"\b(?:{_NOT_USED}|"
    r"exemptions?|allowances?|(?:trips?|abroad|away|travel+ed) (?:this|last|in the (?:last|past)) (?:year|month|30 days)|"
    r"last 30 days|past month|earlier this month|(?:another|other|previous) trip|(?:days|weeks) ago)\b",
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
        if getattr(p, name, None) is not None and not (
            HISTORY.search(question or "") or last_trip_long_ago(question)
        ):
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


def _word_sizes_ml(q: str) -> set:
    """Sizes said in words ("a fifth", "magnum", "half bottle"), in ml."""
    from src.tools.normalise_units import size_ml

    out = set()
    for m in SIZE_WORDS.finditer(q or ""):
        w = re.sub(r"^(?:a|one)\s+", "", m.group(1).lower()).replace("-", " ")
        w = {"minis": "miniature", "mini": "miniature", "nips": "nip"}.get(w, w)
        w = re.sub(r"s$", "", w)
        w = {"litre bottle": "litre", "liter bottle": "litre", "liter": "litre"}.get(
            w, w
        )
        ml = size_ml(1, w)
        if ml is not None:
            out.add(ml)
    return out


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
        from src.tools.normalise_units import size_ml

        # a size the question does not state ("25-year-old" read as 25 ml, D2-048), in ml
        said = {size_ml(x["value"], x["unit"]) for x in stated} | _word_sizes_ml(q)
        for i in alcohol:
            sz = basket[i].size
            ml = size_ml(sz.value, sz.unit) if sz is not None else None
            if sz is not None and stated and ml is not None and ml not in said:
                changes.append(
                    f"item {i + 1} size {sz.value:g} {sz.unit} dropped (not a size in the question)"
                )
                basket[i] = basket[i].model_copy(update={"size": None})
        lacking = [i for i in alcohol if basket[i].size is None]
        distinct = {(x["value"], x["unit"]) for x in stated}
        pairs: list[tuple[int, dict]] = []
        if lacking and stated:
            if len(distinct) == 1:
                pairs = [(i, stated[0]) for i in lacking]
            elif len(stated) == len(alcohol):
                pairs = [(i, stated[alcohol.index(i)]) for i in lacking]
            elif (
                len(alcohol) == 1
            ):  # one item, several sizes ("50 ml each ... under 150 ml?"): the nearest after its name
                pos = [m.start() for m in SIZE.finditer(q)]
                words = [
                    w
                    for w in re.findall(r"[A-Za-zÀ-ÿ]+", basket[alcohol[0]].item or "")
                    if len(w) > 2
                ]
                at = max((q.lower().find(w.lower()) for w in words), default=-1)
                after = [k for k, p0 in enumerate(pos) if p0 > at] if at >= 0 else []
                pairs = [(alcohol[0], stated[after[0] if after else 0])]
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
    # explicit export wording, or US-made cigarettes bought at a duty-free shop (sold for export).
    # Not "made in the US" alone (agent v2, dev-v2 D2-091: American goods returned)
    r"\b(?:for export|export(?:ed)?[- ]label\w*|label+ed for export|stamped for export|tax[- ]exempt for export|"
    r"not for sale in the (?:us|u\.s\.|united states))\b"
    r"|(?=[\s\S]*\bduty[- ]?free\b)[\s\S]*?\b(?:us[- ]made|u\.s\.[- ]made|made in (?:the )?(?:usa|us|u\.s\.|united states|america)|"
    r"american[- ](?:made|brand)\w*|american cigarettes)\b",
    re.IGNORECASE,
)
AMERICAN_RETURNED = re.compile(
    r"\b(?:american goods returned|us goods returned|made in (?:the )?(?:usa|us|u\.s\.|united states)|"
    r"(?:bought|purchased) (?:it|them|these) in the (?:us|u\.s\.|states)|originally (?:from|bought in) the (?:us|u\.s\.|states))\b",
    re.IGNORECASE,
)
# the traveller's own claim switches the AGR rule on (agent v2, dev-v2 D2-091, D2-094)
AGR_CLAIM = re.compile(
    r"\b(?:american|us|u\.s\.) goods returned\b|\bgoods returned\b|\b(?:qualify|count|counts) as american\b",
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
        stated = (
            origin_stated(b, question) if only is None else b.origin in named
        )  # first message: said where it was made; later turn: the country is in the reply
        if "origin" in fields and b.origin and _risk_line(b) and not stated:
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
        if (
            "claims_american_goods_returned" in fields
            and b.category == "tobacco"
            and not b.claims_american_goods_returned
            and AGR_CLAIM.search(question or "")
        ):
            upd["claims_american_goods_returned"] = True
            notes.append(f"item {i + 1} claims_american_goods_returned set (stated)")
        if upd:
            basket[i] = b.model_copy(update=upd)
    if not notes:
        return r, []
    return r.model_copy(update={"basket": basket}), notes


NOT_USED = re.compile(rf"\b(?:{_NOT_USED})\b", re.IGNORECASE)

_MONTHS = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]
LAST_DATE = re.compile(
    r"\b(?:(?:last|previous|prior) (?:\w+ ){0,4}?(?:was|went|in)|"
    rf"{_NEG} (?:\w+ ){{0,4}}?since|(?:no|nothing|only) (?:\w+ ){{0,5}}?since|"
    r"(?:first|only) (?:\w+ ){0,4}?since)\s+(?:(?:back |early |late |mid-?)?in\s+)?(?:the |a |an |last )?"
    rf"(?:\w+ ){{0,2}}?(?:(?P<month>{'|'.join(_MONTHS)})(?:,?\s+(?P<year>(?:19|20)\d\d))?|(?P<year2>(?:19|20)\d\d))\b",
    re.IGNORECASE,
)


def last_trip_long_ago(question: str, today=None) -> bool:
    """A last trip dated at least two calendar months back ("last trip was in January", "last time
    was 2023", "haven't left the US since 2022"), counted from today (the questions say no date)."""
    import datetime as dt

    today = today or dt.datetime.now(dt.UTC).date()
    for m in LAST_DATE.finditer(question or ""):
        month, year = m.group("month"), m.group("year") or m.group("year2")
        y = int(year) if year else today.year
        if month:
            mo = _MONTHS.index(month.lower()) + 1
            if not year and mo > today.month:
                y -= 1  # "in October" said in March: last October
        else:
            mo = 12  # a year alone: at the latest its December
        months_back = (today.year - y) * 12 + today.month - mo
        if months_back >= 2:
            return True
    return False


def history_from_question(
    r: IntakeResult, question: str
) -> tuple[IntakeResult, list[str]]:
    """'first trip this year', 'no other trips', 'haven't used my exemption': not used in the last
    30 days, set in code when the model left it empty (the intake prompt asks the same)."""
    p = r.profile
    if p.exemption_used_last_30_days is not None or not (
        NOT_USED.search(question or "") or last_trip_long_ago(question)
    ):
        return r, []
    return (
        r.model_copy(
            update={
                "profile": p.model_copy(update={"exemption_used_last_30_days": False})
            }
        ),
        ["exemption_used_last_30_days: not used (stated in the question)"],
    )


# Flat rate history (SPEC 3): stated outright, it overrides the default (= exemption history).
# "paid no duty that time" means the flat rate was not used, though the exemption was.
NO_DUTY_PAID = re.compile(
    r"\b(?:paid no (?:duty|tax(?:es)?)|no (?:duty|tax(?:es)?) (?:was |were )?(?:paid|owed|charged)|"
    rf"{_NEG} (?:have to |need to )?(?:pay|owe) (?:any |the )?(?:duty|tax(?:es)?|anything)|"
    r"(?:nothing|no duty) to pay (?:that|last) time|owed nothing|without paying (?:any )?duty)\b",
    re.IGNORECASE,
)
DUTY_PAID = re.compile(
    r"\b(?:paid (?:\$?\d[\d,]*(?:\.\d+)? (?:in |of )?)?(?:the |some |a little )?(?:duty|tax(?:es)?|flat[- ]rate|3 ?%)|"
    r"(?:used|claimed) the flat[- ]rate|was charged (?:the )?(?:duty|flat[- ]rate))\b",
    re.IGNORECASE,
)


def flat_rate_from_question(
    r: IntakeResult, question: str, drop_unstated: bool = True
) -> tuple[IntakeResult, list[str]]:
    """Set flat_rate_used_last_30_days from what the question says about duty paid on the earlier
    trip; drop the model's value when it says nothing (the default then follows the exemption).
    A later turn (drop_unstated=False) only sets it when the message says so."""
    p, q = r.profile, question or ""
    if NO_DUTY_PAID.search(q):
        want, why = False, "no duty paid on the earlier trip (stated)"
    elif DUTY_PAID.search(q):
        want, why = True, "duty paid on the earlier trip (stated)"
    elif drop_unstated:
        want, why = None, "nothing said about duty paid earlier: follows the exemption"
    else:
        return r, []
    if p.flat_rate_used_last_30_days == want:
        return r, []
    return (
        r.model_copy(
            update={
                "profile": p.model_copy(update={"flat_rate_used_last_30_days": want})
            }
        ),
        [
            f"flat_rate_used_last_30_days: {p.flat_rate_used_last_30_days} -> {want} ({why})"
        ],
    )


_COUNT_WORD = r"\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
PACKS_OF = re.compile(
    rf"\b(?:{_COUNT_WORD})\s+(box(?:es)?|packs?|tins?|cases?|bundles?)\s+of\s+(\d+)\b",
    re.IGNORECASE,
)


def pack_counts_from_question(
    r: IntakeResult, question: str, drop_invented: bool = True
) -> tuple[IntakeResult, list[str]]:
    """ "6 boxes of 25 cigars" read by the model as 6 "box": the count per box is in the question.
    Only for tobacco lines whose unit is a bare container word, and only when one count is stated
    for that container word (more than one would need pairing by item). A later turn
    (drop_invented=False) keeps counts from earlier turns: its message need not repeat them."""
    numbers = set(re.findall(r"\d+", question or "")) | spelled_numbers(question or "")
    found: dict[str, set[int]] = {}
    for m in PACKS_OF.finditer(question or ""):
        word = re.sub(r"(?:es|s)$", "", m.group(1).lower())
        found.setdefault(word, set()).add(int(m.group(2)))
    changes: list[str] = []
    basket = list(r.basket)
    for i, b in enumerate(basket):
        unit = (b.quantity.unit or "").strip().lower()
        m = re.fullmatch(r"(box|pack|tin|case|bundle)(?:es|s)? of (\d+)(?: \w+)?", unit)
        if (
            drop_invented
            and b.category == "tobacco"
            and m
            and m.group(2) not in numbers
        ):
            # a count per box the question never gives ("about $180 a box" -> "box of 10")
            basket[i] = b.model_copy(
                update={"quantity": b.quantity.model_copy(update={"unit": m.group(1)})}
            )
            changes.append(
                f"item {i + 1} unit {unit!r} -> {m.group(1)!r} (count not in the question)"
            )
            continue
        price = b.unit_price_usd
        if (
            b.category == "tobacco"
            and unit.rstrip("s") in ("cigar", "cigarette", "stick", "piece")
            and b.quantity.value > 1
            and price is not None
            and not found
        ):
            # "9 cigars, $180 for the box": one box of 9 at $180, not 9 at $180 each (D2-055)
            amount = f"{price:g}".replace(".", r"\.")
            pm = re.search(
                rf"\$\s?{amount}(?:\.00)?\s*(?:for (?:the|a|one|each|that)|a|per|the|each)\s+(box|pack|carton|tin|case)\b",
                question or "",
                re.IGNORECASE,
            )
            if pm:
                n = int(b.quantity.value)
                new = f"{pm.group(1).lower()} of {n}"
                basket[i] = b.model_copy(update={"quantity": Amount(value=1, unit=new)})
                changes.append(
                    f"item {i + 1} {n} {unit} at ${price:g} each -> 1 {new} at ${price:g} (price per {pm.group(1).lower()} in the question)"
                )
                continue
        word = re.sub(r"(?:es|s)$", "", unit)
        if b.category != "tobacco" or word not in found or len(found[word]) != 1:
            continue
        n = next(iter(found[word]))
        new = f"{word} of {n}"
        basket[i] = b.model_copy(
            update={"quantity": b.quantity.model_copy(update={"unit": new})}
        )
        changes.append(
            f"item {i + 1} unit {unit!r} -> {new!r} (stated in the question)"
        )
    if not changes:
        return r, []
    return r.model_copy(update={"basket": basket}), changes


SOFT_DRINK = re.compile(
    r"\b(?:non-?alcoholic|alcohol[- ]free|ginger ale|root beer|birch beer|0\.0 ?%?)\b",
    re.IGNORECASE,
)

# Item names the model writes instead of the product: the category, a list letter, a container.
GENERIC_NAME = re.compile(
    r"^\s*(?:\(?[a-z]\)?|\d+|alcohol|alcoholic drinks?|tobacco|items?|products?|drinks?|liquor|booze|"
    r"bottles?|cans?|cartons?|packs?|boxes?|goods|stuff|other)\s*$",
    re.IGNORECASE,
)
MENTION = re.compile(
    rf"\b(?:{_COUNT_WORD}|a couple of|a six-pack of|a 6-pack of|six|several)\s+"
    r"(?:\d+(?:\.\d+)?\s*(?:ml|cl|l|litre|liter|oz)\s+)?"
    r"(?:(?:half[- ])?bottles?|cans?|fifths?|magnums?|miniatures?|minis|nips?|litres?|liters?|cartons?|packs?|"
    r"boxes|box|tins?|six-packs?|6-packs?|cases?|jars?|flasks?|tall cans?)\s+of\s+"
    r"(?:\d+\s+)?(?P<name>[A-Za-zÀ-ÿ'’&.-]+(?:\s+[A-Za-zÀ-ÿ'’&.-]+){0,5}?)"
    r"(?=\s*[(),.;:!?]|\s+(?:at|for|from|made|bought|brewed|distilled|produced|and|plus|which|that|each|in|on|with|\d)\b|\s*$)",
    re.IGNORECASE,
)


def names_from_question(
    r: IntakeResult, question: str
) -> tuple[IntakeResult, list[str]]:
    """When the model names an item by its category ("alcohol"), a list letter ("a") or a
    container, take the product name from the question ("2 bottles of oloroso sherry"), paired in
    order, only when the question names as many products as the basket has lines (agent v2,
    dev-v2: the name rules and the card need the product's name)."""
    if not any(GENERIC_NAME.match(b.item or "") for b in r.basket):
        return r, []
    names = [m.group("name").strip(" .'’") for m in MENTION.finditer(question or "")]
    if len(names) != len(r.basket):
        return r, []
    changes: list[str] = []
    basket = list(r.basket)
    for i, (b, name) in enumerate(zip(basket, names, strict=True)):
        if GENERIC_NAME.match(b.item or "") and name:
            basket[i] = b.model_copy(update={"item": name})
            changes.append(
                f"item {i + 1} name {b.item!r} -> {name!r} (from the question)"
            )
    return r.model_copy(update={"basket": basket}), changes


def types_from_names(r: IntakeResult) -> tuple[IntakeResult, list[str]]:
    """Product names with a fixed tax class set the line's type (rates.yaml classes_by_name):
    Champagne is sparkling wine, a liqueur is a spirit whatever its ABV, sake is (rice) wine taxed
    as beer. The model often gets these wrong (Day 10: Champagne as still wine, liqueurs as
    "other", sake as spirits)."""
    from src.tools.normalise_units import class_by_name

    changes: list[str] = []
    basket = list(r.basket)
    for i, b in enumerate(basket):
        if (
            b.category == "tobacco"
        ):  # "Montecristo No. 4 cigars" typed cigarettes (dev-v2 D2-037)
            name = (b.item or "").lower()
            want = (
                "cigarettes"
                if re.search(r"\bcigarettes?\b", name)
                else "cigars"
                if re.search(r"\bcigars?\b|\bcigarillos?\b", name)
                else None
            )
            if want and b.type != want:
                basket[i] = b.model_copy(update={"type": want})
                changes.append(f"item {i + 1} {b.item!r}: {b.type} -> {want} (named)")
            continue
        if SOFT_DRINK.search(b.item or ""):
            continue
        entry = class_by_name(b.item)
        if not entry:
            continue
        upd = {}
        if b.type != entry["type"]:
            upd["type"] = entry["type"]
        if b.category != "alcohol":
            upd["category"] = "alcohol"
        if upd:
            basket[i] = b.model_copy(update=upd)
            changes.append(
                f"item {i + 1} {b.item!r}: {b.category}/{b.type} -> alcohol/{entry['type']} (named product, {entry['class']} tax class)"
            )
    if not changes:
        return r, []
    return r.model_copy(update={"basket": basket}), changes


MADE_IN = re.compile(
    r"\b(?:made|produced|distilled|brewed|bottled|crafted|rolled|hand[- ]rolled|manufactured|grown|hecho)\s+"
    r"(?:and\s+bought\s+|right\s+|locally\s+)?(?:in|on|en)\s+(?:the\s+)?"
    r"([A-Za-zÀ-ÿ' .-]{2,40})",
    re.IGNORECASE,
)
MADE_THERE = re.compile(
    r"\b(?:made|produced|distilled|brewed|bottled)\s+(?:there|locally|on the island|in the country)\b|"
    r"\blocal(?:ly[- ](?:made|produced|distilled|brewed))?\b|\b(?:home[- ]?grown|domestic)\b|"
    r"\b(?:there|over there)\s+(?:runs|costs|goes for|sells for|is about|is around)\b",  # what-if: the local price
    re.IGNORECASE,
)


def _zero_duty_countries() -> set[str]:
    from src.tools.common import rates

    return {c for p in rates()["free_programs"].values() for c in p["countries"]}


def _origin_by_name(item: str) -> set[str]:
    """Countries a product name can only come from (rates.yaml origin_by_name: tequila -> MX)."""
    from src.tools.common import rates
    from src.tools.normalise_units import _plain

    name = _plain(item)
    out: set[str] = set()
    for e in rates()["flat_rate"].get("origin_by_name", {}).get("entries", []):
        if any(
            re.search(rf"(?<![a-z]){re.escape(n)}(?![a-z])", name) for n in e["names"]
        ):
            out |= set(e["countries"])
    return out


def _adjectives(code: str) -> list[str]:
    """Demonyms for a country ("mexican", "south korean"), not its place names ("mexico")."""
    import pycountry

    names = {
        n.lower()
        for c in [pycountry.countries.get(alpha_2=code)]
        if c
        for n in (
            c.name,
            getattr(c, "common_name", ""),
            getattr(c, "official_name", ""),
        )
        if n
    }
    places = {
        "korea",
        "south korea",
        "republic of korea",
        "dominican republic",
        "holland",
    }
    return [
        k
        for k, v in ALIASES.items()
        if v == code
        and k not in names
        and k not in places
        and re.fullmatch(r"[a-z ]+", k)
    ]


def _place_names(code: str) -> list[str]:
    """Regex alternatives for a country's names and aliases ("poland", "south korea")."""
    out = [k for k, v in ALIASES.items() if v == code and re.fullmatch(r"[a-z ]+", k)]
    try:
        import pycountry

        c = pycountry.countries.get(alpha_2=code)
        if c:
            out += [n.lower() for n in (c.name, getattr(c, "common_name", "")) if n]
    except ImportError:  # pragma: no cover
        pass
    return [re.escape(n).replace(r"\ ", r"\s+") for n in dict.fromkeys(out)]


def _bought(b: BasketLine, default: str) -> str:
    """The country it was bought in, as a code; a place name or nothing counts as unknown."""
    w = b.bought_where or ""
    return w if re.fullmatch(r"[A-Z]{2}", w) else default


def origin_stated(b: BasketLine, question: str) -> bool:
    """Does the question say where this item was made? A demonym next to the item ("Mexican
    tequila", "Cuban cigars", even when the model named the item "tobacco"), "<item> from Poland",
    "made in Mexico" / "Korean-made", "made there" / "local" for the country it was bought in, a
    product made only there (tequila), or the country in the item's own name."""
    q, code = question or "", b.origin
    if not code:
        return False
    if code in _origin_by_name(b.item) or code in countries_in(b.item):
        return True
    heads = [
        re.escape(w)
        for w in re.findall(r"[a-zà-ÿ]+", (b.item or "").lower())
        if len(w) > 2 and not GENERIC_NAME.match(w)
    ]
    if b.type in PRODUCT_WORDS:
        heads.append(f"(?:{PRODUCT_WORDS[b.type]})")
    places = _place_names(code)
    if (
        heads
        and places
        and re.search(
            rf"\b(?:{'|'.join(heads)})\s+(?:[\w'-]+\s+){{0,2}}?from\s+(?:the\s+)?(?:{'|'.join(places)})\b",
            q,
            re.IGNORECASE,
        )
    ):
        return True  # "vodka from Poland"
    for adj in _adjectives(code):
        a = re.escape(adj).replace(r"\ ", r"\s+")
        if re.search(
            rf"\b{a}[- ](?:made|produced|distilled|brewed)\b", q, re.IGNORECASE
        ):
            return True  # "Korean-made"
        if heads and re.search(
            rf"\b{a}\b(?![- ]republic)\s+(?:[\w'-]+\s+){{0,3}}?(?:{'|'.join(heads)})",
            q,
            re.IGNORECASE,
        ):
            return True  # "Mexican anejo tequila", "Dominican rum"
    for m in MADE_IN.finditer(q):
        if code in countries_in(m.group(1)):
            return True
    for adj in _adjectives(
        code
    ):  # "Everything Italian, bought in Italy", "all of it Cuban"
        a = re.escape(adj).replace(r"\ ", r"\s+")
        if re.search(
            rf"\b(?:everything|all of it|all of them|all|both)(?:\s+(?:is|are|was|were|'s))?\s+{a}\b",
            q,
            re.IGNORECASE,
        ):
            return True
    if (
        code == b.bought_where
        and heads
        and re.search(
            rf"\b(?:{'|'.join(heads)})\s+(?:there|over there|locally)\b",
            q,
            re.IGNORECASE,
        )
    ):
        return True  # what-if: "Carmenere there runs about $15"
    return bool(code == _bought(b, code) and MADE_THERE.search(q))


def origin_free_from_question(
    r: IntakeResult, question: str
) -> tuple[IntakeResult, list[str]]:
    """SPEC v2 row 11: an alcohol line whose origin is a 0%-duty country (USMCA, CAFTA-DR, the
    other 9816.00.20 programmes) keeps it only when the question says where it was made. The model
    otherwise copies the country it was bought in ("whisky at the Cancun duty-free" -> MX, 0%),
    which can under-charge; dropped, the origin is asked when something is owed (SPEC 5.2)."""
    free = _zero_duty_countries()
    notes: list[str] = []
    basket = list(r.basket)
    for i, b in enumerate(basket):
        if (
            b.category != "alcohol"
            or b.origin not in free
            or origin_stated(b, question)
        ):
            continue
        basket[i] = b.model_copy(update={"origin": None})
        notes.append(
            f"item {i + 1} origin {b.origin} dropped (0%-duty country, where it was made not stated)"
        )
    if not notes:
        return r, []
    return r.model_copy(update={"basket": basket}), notes


_HOURS = {"hour": 1, "day": 24, "week": 168}
TRIP_SPAN = re.compile(
    rf"(?<!in the last )(?<!in the past )(?<!within )(?<!since )\b(?P<n>\d+(?:\.\d+)?|{_COUNT_WORD}|a couple of)"
    r"[\s-]*(?P<u>hours?|hrs?|days?|weeks?|wks?)\b(?!\s+ago)",
    re.IGNORECASE,
)
_WORD_N = {w: i for i, w in enumerate(_UNITS)} | {"a": 1, "an": 1, "a couple of": 2}


def trip_from_question(
    r: IntakeResult, question: str
) -> tuple[IntakeResult, list[str]]:
    """An explicit trip length in the question wins over the model's reading: "a 36-hour weekend
    trip" was read as 2 days (agent v2, dev-v2 D2-047), which moves the 48-hour line. Only when the
    question states exactly one length and the model's differs from it."""
    p = r.profile
    if p.trip is None:
        return r, []
    spans = []
    for m in TRIP_SPAN.finditer(question or ""):
        n = m.group("n").lower()
        val = float(n) if n[0].isdigit() else _WORD_N.get(n)
        unit = m.group("u").lower().rstrip("s")
        unit = {"hr": "hour", "wk": "week"}.get(unit, unit)
        if val:
            spans.append((val, unit))
    hours = {v * _HOURS[u] for v, u in spans}
    model_h = p.trip.value * _HOURS[p.trip.unit.rstrip("s")]
    if len(hours) != 1 or model_h in hours:
        return r, []
    val, unit = spans[0]
    new = p.trip.model_copy(update={"value": val, "unit": unit + "s"})
    return (
        r.model_copy(update={"profile": p.model_copy(update={"trip": new})}),
        [
            f"trip {p.trip.value:g} {p.trip.unit} -> {val:g} {unit}s (stated in the question)"
        ],
    )


WHATIF_ASK = re.compile(
    r"\bhow many\b|\bhow much (?:\w+ ){0,3}can (?:i|we) (?:bring|buy|carry|take)\b|"
    r"\b(?:max(?:imum)?|most|largest number)\b.{0,40}\b(?:bring|buy|carry|take)\b",
    re.IGNORECASE,
)


def whatif_from_question(
    r: IntakeResult, question: str
) -> tuple[IntakeResult, list[str]]:
    """A what-if target only when the traveller asks how many they can bring ("how many bottles
    and owe less than $5"); "since I'm way under $200, are they free?" is not one (D2-047)."""
    if r.owe_less_than_usd is None or WHATIF_ASK.search(question or ""):
        return r, []
    return (
        r.model_copy(update={"owe_less_than_usd": None}),
        [f"owe_less_than_usd {r.owe_less_than_usd:g} dropped (no 'how many' question)"],
    )
