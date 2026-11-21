"""The JSON answer every baseline (and later the agent) returns, as scored by eval/score.py."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from src.schemas import BasketLine, Profile

Outcome = Literal["answered", "clarify", "refused", "escalated"]
LineType = Literal[
    "owe", "nothing_to_pay", "prohibited", "declare_detention_risk", "relinquish_excess"
]
Fact = Literal[
    "age",
    "trip_length",
    "exemption_used_last_30_days",
    "origin",
    "abv",
    "size",
    "unit_price",
    "count",
]  # the last three only come from the agent's tools (baseline prompts list the first five)

MAX_CITATIONS = 6  # a real answer needs a few; this stops runaway repetition ("10.115(a)(1)", "(a)(2)", ...)
Citations = Annotated[
    list[str],
    AfterValidator(lambda v: list(dict.fromkeys(v))[:MAX_CITATIONS]),
    Field(json_schema_extra={"maxItems": MAX_CITATIONS}),
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LineResult(Strict):
    line: int = Field(
        description="1-based position of the item in the traveller's question"
    )
    item: str
    type: LineType


class WhatIfAnswer(Strict):
    max_units: int
    owed_usd: float


class Answer(Strict):
    outcome: Outcome
    bottom_line: list[LineResult] = Field(
        default_factory=list, description="One entry per item, in order"
    )
    duty_usd: float | None = Field(
        None, description="Total duty for the basket, to the cent; 0 if none"
    )
    excise_usd: float | None = Field(
        None, description="Total federal excise for the basket, to the cent; 0 if none"
    )
    total_usd: float | None = Field(None, description="duty_usd + excise_usd")
    whatif: WhatIfAnswer | None = None
    clarify_facts: list[Fact] = Field(default_factory=list)
    citations: Citations = Field(
        default_factory=list, description='e.g. "19 CFR 148.33", "HTSUS 9816.00.20"'
    )
    state_flag: str | None = Field(
        None, description="Two-letter arrival state, if its own alcohol rules apply"
    )
    message: str = Field("", description="Short answer for the traveller")


class Reasoned(Strict):
    """cot_sc: reasoning first, then the answer."""

    reasoning: str
    answer: Answer


# ---------------------------------------------------------------- decompose


class Extracted(Strict):
    """decompose step 1: what kind of request, and the facts as stated."""

    request_kind: Literal["assess", "evasion", "injection", "out_of_scope"]
    profile: Profile
    basket: list[BasketLine] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def zero_means_unknown(cls, data: object) -> object:
        """Small models write 0 for "not stated"; treat it as null rather than failing validation."""
        if not isinstance(data, dict):
            return data
        prof = data.get("profile") or {}
        if (
            isinstance(prof.get("trip"), dict)
            and not (prof["trip"].get("value") or 0) > 0
        ):
            prof["trip"] = None
        basket = []
        for ln in data.get("basket") or []:
            if (
                not isinstance(ln, dict)
                or not ((ln.get("quantity") or {}).get("value") or 0) > 0
            ):
                continue  # a line with no quantity is not an item
            if (
                isinstance(ln.get("size"), dict)
                and not (ln["size"].get("value") or 0) > 0
            ):
                ln["size"] = None
            if ln.get("abv") is not None and ln["abv"] <= 0:
                ln["abv"] = None
            basket.append(ln)
        data["basket"] = basket
        return data


class LineDecision(Strict):
    line: int
    item: str
    status: Literal[
        "exempt",
        "partly_exempt",
        "dutiable",
        "prohibited",
        "declare_detention_risk",
        "relinquish_excess",
    ]
    excess_liters: float | None = None
    note: str = ""


class RulesDecision(Strict):
    """decompose step 2: which rules apply (no amounts yet)."""

    missing_facts: list[Fact] = Field(default_factory=list)
    escalate: bool = False
    exemption: Literal["800", "200", "none"]
    alcohol_allowance_liters: float | None = None
    lines: list[LineDecision] = Field(default_factory=list)
    citations: Citations = Field(default_factory=list)
