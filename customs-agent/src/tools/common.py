"""Shared helpers for the tools: data loading, Decimal rounding, rule matching, ToolError.

Rules and rates are data (CLAUDE.md rule 3): every threshold and rate comes from
data/rules.yaml or data/rates.yaml, never from a constant in code.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class ToolError(Exception):
    """A tool could not produce an answer.

    code: missing_fact | out_of_scope | escalate | invalid_input
    missing: fact names the traveller must supply (docs/SPEC.md 5.2 order)
    rule_id: the rules.yaml rule behind an escalation, if any
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        missing: list[str] | None = None,
        rule_id: str | None = None,
        citations: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.missing = missing or []
        self.rule_id = rule_id
        self.citations = citations or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": self.message,
            "missing": self.missing,
            "rule_id": self.rule_id,
            "citations": self.citations,
        }


@lru_cache(maxsize=4)
def _load(name: str, data_dir: str) -> dict[str, Any]:
    return yaml.safe_load((Path(data_dir) / name).read_text())


def rules(data_dir: Path = DATA_DIR) -> dict[str, Any]:
    return _load("rules.yaml", str(data_dir))


def rates(data_dir: Path = DATA_DIR) -> dict[str, Any]:
    return _load("rates.yaml", str(data_dir))


# ------------------------------------------------------------------ numbers


def dec(x: float | str | Decimal) -> Decimal:
    """Exact Decimal from a stated number (via str, so 0.1 stays 0.1)."""
    return x if isinstance(x, Decimal) else Decimal(str(x))


def cents(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def dollars(x: Decimal) -> Decimal:
    return x.quantize(Decimal(1), rounding=ROUND_HALF_UP)


def litres(x: Decimal) -> Decimal:
    """Volumes kept to the millilitre."""
    return x.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------ facts


def order_missing(names: list[str]) -> list[str]:
    from src.schemas import FACT_ORDER

    seen = list(dict.fromkeys(names))
    return sorted(
        seen, key=lambda n: FACT_ORDER.index(n) if n in FACT_ORDER else len(FACT_ORDER)
    )


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


# ------------------------------------------------------------------ rules


def rule(rule_id: str) -> dict[str, Any]:
    for r in rules()["restrictions"]:
        if r["id"] == rule_id:
            return r
    raise KeyError(rule_id)


def match(when: dict[str, Any], ctx: dict[str, Any]) -> str:
    """Evaluate a rules.yaml `when` block against what a tool knows.

    Returns "n/a" when the rule uses a key this tool does not supply (another stage
    evaluates it), "unknown" when a needed fact is missing, else "yes" or "no".
    """
    if any(k not in ctx for k in when):
        return "n/a"
    unknown = False
    for key, want in when.items():
        have = ctx[key]
        if have is None:
            unknown = True
            continue
        if key == "max_age":
            ok = have <= want
        elif key.endswith("_gt"):
            ok = have > want
        elif isinstance(want, list):
            ok = have in want
        else:
            ok = have == want
        if not ok:
            return "no"
    return "unknown" if unknown else "yes"
