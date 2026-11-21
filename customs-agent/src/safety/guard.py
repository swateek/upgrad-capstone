"""Guard: refuse evasion and injection, and give a scope note for out-of-scope questions, in code.

Runs before intake, so a hostile question never reaches the model (SPEC 5.3: injection in the
question is refused before the model call). The intake model's `request_kind` is a second line
of defence for phrasings these patterns miss.

The patterns are written from the SPEC categories (rules.yaml -> out_of_scope), not from eval
questions (CLAUDE.md rule 6). A false refusal is cheaper than advice on evading customs, but the
patterns stay narrow: "do I have to declare it?" is a normal question.

sanitise_clause() checks retrieved text: an official regulation never addresses an AI assistant,
so a chunk that does is dropped before the writer sees it (injection in a document: ignore).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_I = re.IGNORECASE


def _any(patterns: list[str]) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{p})" for p in patterns), _I)


INJECTION = _any(
    [
        r"</?\s*(system|assistant|instructions?)\s*>",
        r"\b(ignore|disregard|forget|override)\b.{0,30}\b(instructions?|rules|prompt|guidelines|above|previous)\b",
        r"\bnew (rule|instruction)s?\s*:",
        r"\bsystem (prompt|message|notice|override)\b",
        r"\byou (are now|must now|will now|must say|must answer)\b",
        r"\b(developer|jailbreak|dan) mode\b",
        r"\bpretend (you are|to be|that)\b",
        r"\b(say|tell me|answer|respond)\b.{0,20}\b(everything|it'?s|it is|they'?re|all)\b.{0,15}\bduty[- ]?free\b",
    ]
)

EVASION = _any(
    [
        r"\b(hide|hiding|hidden|conceal\w*|smuggl\w*|sneak\w*|stash\w*)\b",
        r"\bwithout (getting )?(caught|noticed|detected|declaring)\b",
        r"\b(avoid|skip|evade|dodge|get around|get out of)\b.{0,15}\b(declar\w*|dut(y|ies)|customs|tax(es)?|inspection)\b",
        r"\b(under-?valu\w*|mislabel\w*|fake (receipt|invoice)|lie to|lying to)\b",
        r"\b(tell|say to) (the )?(officer|cbp|customs)\b.{0,30}\b(less|cheaper|gift|not mine|only)\b",
        r"\b(don'?t|do not|not) (want to |going to |plan to )?declare\b",
        r"\bget (it|them|this|these) (past|through) customs\b",
    ]
)

# Travellers and goods outside v1 (rules.yaml -> out_of_scope). Goods only count as out of scope when
# no alcohol or tobacco is mentioned; mixed questions are assessed with a note (SPEC 2).
SCOPE_TRAVELLER = {
    "crew": r"\b(flight attendant|cabin crew|crew ?member|aircrew|airline crew|ship'?s crew|pilot for)\b",
    "non_residents": r"\b(non-?resident|not a (us|u\.s\.) (resident|citizen)|tourist visa|i'?m (a )?(tourist|visitor|visiting the us))\b",
    "insular_possession_arrivals": r"\b(guam|american samoa|northern mariana|saipan|u\.?s\.? virgin islands|usvi|st\.? thomas|st\.? croix|st\.? john\b)",
    "shipped_goods": r"\b(ship(ped|ping)?|mail(ed|ing)?|post(ed|ing)?|courier|send(ing)?)\b.{0,20}\b(home|it|them|back|to the us|to myself)\b.{0,30}\b(instead|separately|by (mail|post)|fedex|dhl|ups)\b|\b(fedex|dhl|ups|usps) (it|them)\b",
    "family_grouping": r"\b(pool|combine|share|add up)\b.{0,25}\b(exemptions?|allowances?)\b",
}
SCOPE_GOODS = {
    "vapes_and_nicotine_products": r"\b(vapes?|vaping|e-?cig\w*|e-?liquid|juul|nicotine pouch\w*|zyn|snus|heated tobacco|iqos)\b",
    "food_and_agriculture": r"\b(cheese|sausage|salami|ham|meat|fruit|vegetables?|seeds?|plants?|honey|chocolate|food)\b",
    "currency": r"\b(cash|currency|\$ ?10,?000|monetary instruments?)\b",
}
ALCOHOL_TOBACCO = re.compile(
    r"\b(wine|beer|ale|lager|cider|sake|spirits?|liquor|liqueur|whisk(e)?y|scotch|bourbon|vodka|gin|rum|tequila|mezcal|brandy|cognac|"
    r"port|sherry|champagne|prosecco|cava|grappa|soju|baijiu|absinthe|alcohol\w*|booze|bottles?|cigar\w*|cigarettes?|tobacco|cartons?|packs?)\b",
    _I,
)

# Document injection: text addressed to an assistant, or telling it what to say.
DOC_INJECTION = _any(
    [
        r"\b(assistants?|ai|chatbots?|language models?|llms?)\b.{0,60}\b(must|should|tell|say|ignore|now)\b",
        r"\bsystem (notice|prompt|message|override)\b",
        r"\b(ignore|disregard)\b.{0,30}\b(instructions?|rules|above|previous)\b",
        r"\btell (the )?(travell?ers?|users?|customers?)\b",
    ]
)

MESSAGES = {
    "injection": "I can't follow instructions to change how I assess customs rules. Ask me about the alcohol or tobacco you are bringing home and I'll work it out.",
    "evasion": "I can't help with avoiding or misleading customs. Declare everything you bring: undeclared goods can be seized and fined. I can tell you what you are likely to owe if you declare.",
    "out_of_scope": "This assistant only covers alcohol and tobacco brought home by a returning US resident in their own baggage. For {what}, see CBP's traveller guidance at cbp.gov.",
}
SCOPE_WHAT = {
    "crew": "crew members' allowances",
    "non_residents": "visitors and non-residents",
    "insular_possession_arrivals": "arrivals from US territories (the $1,600 exemption)",
    "shipped_goods": "goods shipped or mailed separately",
    "family_grouping": "families combining their exemptions",
    "vapes_and_nicotine_products": "vapes and nicotine products",
    "food_and_agriculture": "food and agricultural products",
    "currency": "cash and currency reporting",
}


@dataclass(frozen=True)
class GuardResult:
    action: str  # "pass" | "refuse"
    reason: str | None = None  # injection | evasion | out_of_scope_<category>
    message: str = ""
    other_goods: bool = (
        False  # alcohol/tobacco plus out-of-scope goods: assess, add a note
    )


def check_question(question: str) -> GuardResult:
    q = question or ""
    if INJECTION.search(q):
        return GuardResult("refuse", "injection", MESSAGES["injection"])
    if EVASION.search(q):
        return GuardResult("refuse", "evasion", MESSAGES["evasion"])
    for cat, pat in SCOPE_TRAVELLER.items():
        if re.search(pat, q, _I):
            return GuardResult(
                "refuse",
                f"out_of_scope_{cat}",
                MESSAGES["out_of_scope"].format(what=SCOPE_WHAT[cat]),
            )
    goods = [cat for cat, pat in SCOPE_GOODS.items() if re.search(pat, q, _I)]
    has_at = bool(ALCOHOL_TOBACCO.search(q))
    # "nicotine pouches" mentions no alcohol or tobacco word, but "packs"/"cans" might: vapes win.
    if goods and (
        not has_at
        or goods[0] == "vapes_and_nicotine_products"
        and not _at_besides_vapes(q)
    ):
        cat = goods[0]
        return GuardResult(
            "refuse",
            f"out_of_scope_{cat}",
            MESSAGES["out_of_scope"].format(what=SCOPE_WHAT[cat]),
        )
    return GuardResult("pass", other_goods=bool(goods))


def _at_besides_vapes(q: str) -> bool:
    """Alcohol or tobacco named in a vape question, other than packaging words."""
    hits = {m.group(0).lower() for m in ALCOHOL_TOBACCO.finditer(q)}
    return bool(hits - {"pack", "packs", "carton", "cartons", "bottle", "bottles"})


def sanitise_clause(text: str) -> tuple[bool, str | None]:
    """(keep, why). A retrieved chunk that addresses an assistant is dropped, not edited."""
    m = DOC_INJECTION.search(text or "")
    return (False, m.group(0)) if m else (True, None)
