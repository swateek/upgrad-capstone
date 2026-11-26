"""Pydantic models shared by intake, the tools and (later) the agent.

Quantities and durations are kept as stated ({value, unit}); code converts them
(COMPENSATIONS.md row 3). Money and volumes in tool outputs are Decimal, so the
verifier can match the writer's figures exactly.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["alcohol", "tobacco", "other"]
ProductType = Literal[
    "wine", "sparkling_wine", "beer", "spirits", "cigarettes", "cigars", "other"
]
FactName = Literal[
    "age",
    "trip_length",
    "exemption_used_last_30_days",
    "origin",
    "abv",
    "size",
    "unit_price",
    "count",
]
# Order in which missing facts are asked (docs/SPEC.md 5.2).
FACT_ORDER: tuple[str, ...] = (
    "age",
    "trip_length",
    "exemption_used_last_30_days",
    "origin",
    "abv",
    "size",
    "unit_price",
    "count",
)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ intake


class Amount(Model):
    """A quantity as the traveller stated it: 3 bottle, 70 cl, 2 carton, 1 box of 25."""

    value: float = Field(gt=0)
    unit: str


class Duration(Model):
    value: float = Field(gt=0)
    unit: Literal["hours", "days", "weeks"]


class Profile(Model):
    age: int | None = Field(None, ge=0, le=120)
    trip: Duration | None = None
    direct_arrival_from: str | None = Field(
        None, description="ISO 3166 alpha-2 code of the country flown or driven in from"
    )
    exemption_used_last_30_days: bool | None = None
    flat_rate_used_last_30_days: bool | None = Field(
        None,
        description="Defaults to exemption_used_last_30_days when not stated (SPEC 3)",
    )
    arrival_state: str | None = Field(
        None, description="US state code of the port of arrival"
    )

    @property
    def flat_rate_used(self) -> bool | None:
        if self.flat_rate_used_last_30_days is not None:
            return self.flat_rate_used_last_30_days
        return self.exemption_used_last_30_days


class BasketLine(Model):
    item: str
    category: Category
    type: ProductType
    quantity: Amount = Field(
        description="Number of containers or packs as stated, e.g. 3 bottle, 2 carton"
    )
    size: Amount | None = Field(
        None, description="Container size for alcohol, e.g. 750 ml, 70 cl, 1 fifth"
    )
    abv: float | None = Field(
        None, gt=0, le=100, description="Alcohol by volume, percent"
    )
    unit_price_usd: float | None = Field(
        None, ge=0, description="Price per quantity unit (per bottle, per carton)"
    )
    origin: str | None = Field(
        None, description="Where made (ISO alpha-2); decides duty rate and sanctions"
    )
    bought_where: str | None = None
    export_labelled_us: bool = False
    claims_american_goods_returned: bool = False


class Intake(Model):
    profile: Profile
    basket: list[BasketLine]


# ------------------------------------------------------------------ tool outputs


class NormalisedLine(Model):
    index: int = Field(description="1-based position in the basket")
    line: BasketLine
    units: Decimal = Field(description="Number of containers or packs")
    unit_ml: Decimal | None = None
    total_l: Decimal | None = None
    count: int | None = Field(None, description="Cigarettes or cigars in the line")
    proof: Decimal | None = None
    excise_class: str | None = None


class RuleHit(Model):
    rule_id: str
    outcome: str
    line: int | None = None
    message: str | None = None
    citations: list[str] = []


class Restrictions(Model):
    hits: list[RuleHit] = []
    prohibited_lines: list[int] = []
    escalate: bool = False
    alcohol_excluded: bool = False
    tobacco_excluded: bool = False
    missing: list[str] = []
    citations: list[str] = []


class Exemption(Model):
    kind: Literal["standard_800", "short_trip_200"] | None
    value_usd: Decimal | None = None
    alcohol_l: Decimal = Decimal(0)
    beneficiary_2l: bool = False
    max_cigarettes: int = 0
    max_cigars: int = 0
    max_alcohol_ml: Decimal | None = None
    all_or_nothing: bool = False
    reasons: list[str] = []
    missing: list[str] = []
    citations: list[str] = []


LineStatus = Literal[
    "exempt",
    "partly_exempt",
    "dutiable",
    "prohibited",
    "escalate",
    "declare_detention_risk",
    "relinquish_excess",
]


class LineAllowance(Model):
    line: int
    status: LineStatus
    exempt_l: Decimal | None = None
    excess_l: Decimal | None = None
    exempt_count: int | None = None
    excess_count: int | None = None
    rule_id: str | None = None
    message: str | None = None


class Allowance(Model):
    exemption: Literal["standard_800", "short_trip_200"]
    lines: list[LineAllowance]
    all_or_nothing_failed: bool = False
    alcohol_allowance_l: Decimal = Decimal(0)
    exempt_value_usd: Decimal = Decimal(0)
    reasons: list[str] = []
    citations: list[str] = []


class LineDuty(Model):
    line: int
    excess_l: Decimal
    dutiable_value_usd: Decimal
    duty_rate: Decimal
    duty_basis: str
    duty_usd: Decimal
    excise_class: str
    excise_rate: Decimal
    excise_basis: str
    gallons: Decimal
    proof_gallons: Decimal | None = None
    excise_usd: Decimal
    total_usd: Decimal


class DutyExcise(Model):
    lines: list[LineDuty]
    dutiable_value_usd: Decimal
    duty_usd: Decimal
    excise_usd: Decimal
    total_usd: Decimal
    citations: list[str] = []


class StateFlag(Model):
    state: str
    name: str
    note: str
    source: str
    general_note: str
    citations: list[str] = []


class WhatIf(Model):
    max_units: int
    owed_usd: Decimal
    limit_usd: Decimal
    stopped_by: Literal["target", "commercial_quantity", "max_units"]


class EscalationNote(Model):
    reason: str
    summary: str
    facts: dict
    known: dict = {}


class Clause(Model):
    """One retrieved chunk of regulation text. The writer may cite only these citation_ids."""

    citation_id: str
    chunk_id: str
    heading: str
    text: str
    authority: str
    source_url: str | None = None
    as_of: str | None = None
    tokens: int | None = None
    found_by: Literal["citation_id", "search"]
    rank: int | None = Field(None, description="Rank in the search results (search only)")


class Clauses(Model):
    query: str
    clauses: list[Clause]
    retrieved_ids: list[str] = Field(
        description="citation_ids the writer may cite, in order (CLAUDE.md rule 2)"
    )
    not_found: list[str] = Field(
        [], description="Requested citation_ids missing from the corpus or not citable"
    )
    method: str
    ms: float = 0.0
