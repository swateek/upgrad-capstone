"""The guard (plan §7, SPEC §7): injection, evasion and declaration requests are refused in
code before any model call; banned phrases are blocked by the verifier. Policy:
pack/policy/guard.yaml."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from customs.config import get_settings


@dataclass(frozen=True)
class GuardHit:
    rule: str  # evasion | injection | declaration
    wording: str
    matched: str


class Guard:
    def __init__(self, path: Path | None = None) -> None:
        p = path or get_settings().pack_dir / "policy" / "guard.yaml"
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        self.rules = {
            name: (
                " ".join(spec["wording"].split()),
                [re.compile(rx, re.IGNORECASE) for rx in spec["patterns"]],
            )
            for name, spec in doc["refusals"].items()
        }
        self.banned = [b.lower() for b in doc.get("banned_phrases", [])]

    def check(self, text: str) -> GuardHit | None:
        norm = text.replace("’", "'")
        for name, (wording, patterns) in self.rules.items():
            for rx in patterns:
                m = rx.search(norm)
                if m:
                    return GuardHit(name, wording, m.group(0))
        return None

    def banned_in(self, text: str) -> list[str]:
        low = text.lower().replace("’", "'")
        return [b for b in self.banned if re.search(rf"\b{re.escape(b)}", low)]


@lru_cache(maxsize=1)
def get_guard() -> Guard:
    return Guard()
