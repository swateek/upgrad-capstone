"""Typed access to the signed-off rule tables in pack/rules/ (SPEC §5).

The calculators read every limit, rate, unit and country list from here; nothing numeric is
hard-coded in the tools. Monetary and volume values are Decimals.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from customs.config import get_settings


def D(x: Any) -> Decimal:
    return Decimal(str(x))


@dataclass(frozen=True)
class ExciseClass:
    name: str
    rate: Decimal
    per: str  # proof_gallon | wine_gallon | barrel
    min_abv_exclusive: Decimal | None = None
    max_abv: Decimal | None = None


@dataclass(frozen=True)
class Tables:
    rules: dict[str, dict]  # R1..R12 rows by id
    scope_notes: dict[str, Any]
    rates: dict[str, Any]
    units: dict[str, Any]
    countries: dict[str, Any]
    brands: dict[str, Any]
    states: dict[str, dict]
    facts: dict[str, dict]
    as_of: str

    # --- rules ------------------------------------------------------------------------------
    def params(self, rule: str) -> dict:
        return self.rules[rule]["params"]

    def cites(self, rule: str, part: str | None = None) -> list[str]:
        c = self.rules[rule]["cites"]
        if isinstance(c, dict):
            return list(c[part]) if part else [x for v in c.values() for x in v]
        return list(c)

    # --- units ------------------------------------------------------------------------------
    @property
    def litres_per_gallon(self) -> Decimal:
        return D(self.units["litres_per_us_gallon"])

    @property
    def gallons_per_barrel(self) -> Decimal:
        return D(self.units["gallons_per_barrel"])

    def default_abv(self, item: str) -> Decimal | None:
        v = self.units["default_abv"].get(item)
        return None if v is None else D(v)

    # --- rates ------------------------------------------------------------------------------
    @property
    def excise_classes(self) -> dict[str, ExciseClass]:
        out = {}
        for row in self.rates["excise_alcohol"]:
            out[row["class"]] = ExciseClass(
                name=row["class"],
                rate=D(row["rate"]),
                per=row["per"],
                min_abv_exclusive=(
                    D(row["min_abv_exclusive"]) if "min_abv_exclusive" in row else None
                ),
                max_abv=D(row["max_abv"]) if "max_abv" in row else None,
            )
        return out

    @property
    def flat_rate(self) -> Decimal:
        return D(self.rates["duty"]["flat_rate"]["rate"])

    @property
    def column2_rate(self) -> Decimal:
        return D(self.rates["duty"]["column2_flat_rate"]["rate"])

    # --- countries --------------------------------------------------------------------------
    @property
    def cbi_countries(self) -> set[str]:
        cb = self.countries["caribbean_basin"]
        return set(cb[cb["used_by_R2"]]["codes"])

    @property
    def column2(self) -> set[str]:
        return set(self.countries["column2"]["codes"])

    @property
    def insular(self) -> set[str]:
        return set(self.countries["insular_possessions"]["codes"])

    @property
    def mexico(self) -> set[str]:
        return set(self.countries["mexico"])

    @property
    def partner_programs(self) -> dict[str, str]:
        """Country code -> trade-agreement programme symbol (9816.00.20 Special: Free)."""
        out = {}
        for sym, prog in self.countries["trade_agreement_programs"]["programs"].items():
            for code in prog["codes"]:
                out[code] = sym
        return out

    @property
    def ambiguous_brands(self) -> set[str]:
        return {b.casefold() for group in self.brands["ambiguous_brands"].values() for b in group}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def load_tables(rules_dir: Path | None = None) -> Tables:
    d = rules_dir or get_settings().pack_dir / "rules"
    rules_doc = _load(d / "rules.yaml")
    return Tables(
        rules={r["id"]: r for r in rules_doc["rules"]},
        scope_notes=rules_doc.get("scope_notes", {}),
        rates=_load(d / "rates.yaml"),
        units=_load(d / "units.yaml"),
        countries=_load(d / "countries.yaml"),
        brands=_load(d / "brands.yaml"),
        states=_load(d / "states.yaml")["states"],
        facts=_load(d / "facts.yaml")["facts"],
        as_of=str(rules_doc["as_of"]),
    )
