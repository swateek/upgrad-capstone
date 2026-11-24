"""Data shapes for the calculators: the intake schema (SPEC §3) and what the tools produce."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Item = Literal[
    "wine",
    "sparkling_wine",
    "beer",
    "spirits",
    "liqueur",
    "hard_cider",
    "cigarettes",
    "cigars",
    "other",
]
ALCOHOL_ITEMS = {"wine", "sparkling_wine", "beer", "spirits", "liqueur", "hard_cider"}
TOBACCO_ITEMS = {"cigarettes", "cigars"}


class Profile(BaseModel):
    """SPEC §3 profile. trip_hours is a number, or "<48" / ">=48" when only the bucket is known."""

    model_config = ConfigDict(extra="forbid")

    age: int | None = None
    trip_hours: float | Literal["<48", ">=48"] | None = None
    arrived_directly_from: str | None = None  # ISO-2
    countries_visited: list[str] = Field(default_factory=list)
    exemption_used_last_30_days: bool | None = None
    arrival_state: str | None = None
    us_resident: bool = True
    travelling_as_family: bool = False
    # Scope signals the intake may set (SPEC §2 out-of-scope list); not part of the scored facts.
    crew: bool = False
    shipped: bool = False

    @property
    def long_trip(self) -> bool | None:
        if self.trip_hours is None:
            return None
        if isinstance(self.trip_hours, str):
            return self.trip_hours == ">=48"
        return self.trip_hours >= 48


class Line(BaseModel):
    """SPEC §3 basket line. value_usd is for the whole line; origin is where it was MADE."""

    model_config = ConfigDict(extra="forbid")

    item: Item
    quantity: float | None = None
    unit: str | None = None
    container_ml: float | None = None
    abv: float | None = None
    value_usd: float | None = None
    origin: str | None = None  # ISO-2, "unknown", or None
    bought_in: str | None = None  # ISO-2 or "duty_free"
    brand: str | None = None
    us_made_export_labelled: bool | None = None
    # For item "other": which scope note applies (SPEC §2). Not part of the scored facts.
    other_kind: Literal["other_goods", "vapes_nicotine"] = "other_goods"


class NLine(BaseModel):
    """A normalised line (normalise_units)."""

    index: int  # 1-based position in the basket (figure names use it)
    line: Line
    volume_ml: Decimal | None = None  # alcohol
    sticks: int | None = None  # cigarettes or cigars
    abv: Decimal | None = None
    abv_defaulted: bool = False
    container_defaulted: bool = False
    status: Literal[
        "ok", "prohibited", "possibly_cuban", "out_of_scope", "russian_scope", "unknown_quantity"
    ] = "ok"
    prohibited_where: Literal["acquired_in_cuba", "third_country"] | None = None

    @property
    def is_alcohol(self) -> bool:
        return self.line.item in ALCOHOL_ITEMS

    @property
    def is_tobacco(self) -> bool:
        return self.line.item in TOBACCO_ITEMS

    @property
    def admissible(self) -> bool:
        return self.status == "ok"


class Figure(BaseModel):
    name: str  # vocabulary shared with the gold: exemption_usd, dutiable_ml_2, total_owed_usd...
    value: str
    unit: Literal["usd", "ml", "sticks", "rate", "count"]


Outcome = Literal["answered", "clarify", "refused", "out_of_scope", "escalated"]
Kind = Literal[
    "owe",
    "nothing_owed",
    "prohibited",
    "seizure_risk",
    "mixed",
    "refused",
    "out_of_scope",
    "escalated",
    "clarify",
    "whatif",
]


class Assessment(BaseModel):
    """Everything the writer and verifier need; produced by customs.tools.calc.assess."""

    outcome: Outcome
    kind: Kind
    owe_usd: Decimal | None = None
    exemption_usd: int | None = None
    figures: list[Figure] = Field(default_factory=list)
    rule_refs: list[str] = Field(
        default_factory=list
    )  # e.g. ["R9", "R4:third_country", "state:CA"]
    notes: list[str] = Field(default_factory=list)
    lines: list[NLine] = Field(default_factory=list)
    escalation_reason: str | None = None
    defaults_used: list[str] = Field(default_factory=list)  # stated in "facts relied on"

    def figure(self, name: str) -> str | None:
        return next((f.value for f in self.figures if f.name == name), None)
