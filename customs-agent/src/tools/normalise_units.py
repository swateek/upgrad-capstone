"""normalise_units: stated quantities -> containers, ml, litres, pieces, proof, excise class.

"a fifth" -> 750 ml, "70 cl" -> 700 ml, "carton" -> 200 cigarettes, "box of 25" -> 25 cigars.
Conversions come from rates.yaml -> conversions.
"""

from __future__ import annotations

import re
from decimal import Decimal

from pydantic import BaseModel

from src.schemas import BasketLine, NormalisedLine
from src.tools.common import ToolError, dec, litres, rates


class Args(BaseModel):
    basket: list[BasketLine]


def _unit(text: str) -> str:
    u = text.strip().lower()
    u = re.sub(r"\s+", " ", u)
    for plural, single in (
        ("bottles", "bottle"),
        ("cartons", "carton"),
        ("packs", "pack"),
        ("cigarettes", "cigarette"),
        ("cigars", "cigar"),
        ("miniatures", "miniature"),
        ("half bottles", "half bottle"),
        ("fifths", "fifth"),
        ("magnums", "magnum"),
        ("liters", "liter"),
        ("litres", "litre"),
        ("cans", "can"),
        ("boxes", "box"),
    ):
        if u == plural or u.startswith(plural + " "):
            u = single + u[len(plural) :]
    return {
        "millilitre": "ml",
        "milliliter": "ml",
        "millilitres": "ml",
        "milliliters": "ml",
        "centilitre": "cl",
        "centiliter": "cl",
        "litre": "l",
        "liter": "l",
        "oz": "fl oz",
    }.get(u, u)


PIECE_UNITS = {
    "cigar",
    "cigars",
    "cigarette",
    "cigarettes",
    "piece",
    "pieces",
    "stick",
    "sticks",
}
CONTAINER_WORDS = {
    "box",
    "boxes",
    "pack",
    "packs",
    "tin",
    "tins",
    "case",
    "cases",
    "carton",
    "cartons",
}


def size_ml(amount_value: float, unit: str) -> Decimal | None:
    conv = rates()["conversions"]
    u = _unit(unit)
    if u in conv["volume_units_ml"]:
        return dec(amount_value) * dec(conv["volume_units_ml"][u])
    if u in conv["containers_ml"]:
        return dec(amount_value) * dec(conv["containers_ml"][u])
    return None


def excise_class(line: BasketLine) -> str | None:
    """TTB class for an alcohol line; None if the ABV needed to decide it is missing."""
    if line.type == "spirits":
        return "spirits"
    if line.type == "beer":
        return "beer"
    if line.type == "sparkling_wine":
        return "sparkling"
    if line.type == "wine":
        if line.abv is None:
            return None
        if line.abv <= 16:
            return "still_up_to_16_abv"
        if line.abv <= 21:
            return "still_over_16_to_21_abv"
        if line.abv <= 24:
            return "still_over_21_to_24_abv"
        raise ToolError(
            "escalate", f"{line.item}: wine over 24% ABV is not modelled in v1"
        )
    return None


def normalise_line(index: int, line: BasketLine) -> NormalisedLine:
    conv = rates()["conversions"]
    q = line.quantity
    out: dict = {"index": index, "line": line, "units": dec(q.value)}
    if line.category == "alcohol":
        unit = _unit(q.unit)
        direct = size_ml(1, unit) if unit in conv["volume_units_ml"] else None
        per = (
            size_ml(line.size.value, line.size.unit) if line.size is not None else None
        )
        whole = (
            dec(q.value) * direct / per if direct is not None and per else None
        )  # "2 litres" of "1-litre bottles": 2 containers of the stated size
        if whole is not None and whole == whole.to_integral_value() and whole >= 1:
            out["units"], ml = whole.to_integral_value(), per
        elif direct is not None:  # "500 ml of gin": one container of the stated volume
            out["units"], ml = Decimal(1), dec(q.value) * direct
        elif line.size is not None:
            ml = size_ml(line.size.value, line.size.unit)
            if ml is None:
                raise ToolError(
                    "invalid_input",
                    f"{line.item}: unknown size unit '{line.size.unit}'",
                )
        else:
            ml = size_ml(1, unit)  # "a fifth", "2 miniatures"
            if ml is None:
                raise ToolError(
                    "missing_fact",
                    f"{line.item}: container size not stated",
                    missing=["size"],
                )
        out["unit_ml"] = ml
        out["total_l"] = litres(out["units"] * ml / dec(conv["ml_per_liter"]))
        if line.type == "spirits" and line.abv is not None:
            out["proof"] = dec(line.abv) * dec(conv["proof_per_abv_percent"])
        out["excise_class"] = excise_class(line)
    elif line.category == "tobacco":
        unit = _unit(q.unit)
        table = conv["tobacco_units"].get(line.type, {})
        m = re.fullmatch(r"(?:box|pack|tin|case) of (\d+)", unit)
        piece_size = (
            line.size is not None
            and _unit(line.size.unit) in PIECE_UNITS
            and float(line.size.value).is_integer()
            and line.size.value >= 1
        )
        if m:
            per = int(m.group(1))
        elif unit in table:
            per = table[unit]
        elif (
            piece_size and unit in CONTAINER_WORDS
        ):  # 1 "box", size "10 cigars": a box of 10
            per = int(line.size.value)
        else:
            raise ToolError(
                "missing_fact",
                f"{line.item}: how many in a '{q.unit}'?",
                missing=["count"],
            )
        pieces = dec(q.value) * per
        if pieces != pieces.to_integral_value():
            raise ToolError(
                "invalid_input",
                f"{line.item}: {pieces} is not a whole number of pieces",
            )
        out["count"] = int(pieces)
    return NormalisedLine(**out)


def normalise_units(args: Args) -> list[NormalisedLine]:
    return [normalise_line(i, ln) for i, ln in enumerate(args.basket, 1)]
