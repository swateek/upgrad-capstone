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
        self.banned_patterns = [
            re.compile(rx, re.IGNORECASE) for rx in doc.get("banned_patterns", [])
        ]

    def check(self, text: str) -> GuardHit | None:
        """Checks the text as written and with look-alike characters read as letters ("h1de",
        "sm0ggle", red-team 18 Nov)."""
        norm = text.replace("\u2019", "'")
        for variant in dict.fromkeys([norm, deleet(norm)]):
            for name, (wording, patterns) in self.rules.items():
                for rx in patterns:
                    m = rx.search(variant)
                    if m:
                        return GuardHit(name, wording, m.group(0))
        return None

    def banned_in(self, text: str) -> list[str]:
        low = text.lower().replace("\u2019", "'")
        found = [b for b in self.banned if re.search(rf"\b{re.escape(b)}", low)]
        found += [m.group(0) for rx in self.banned_patterns if (m := rx.search(low))]
        return found


LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a",
                      "$": "s"})  # fmt: skip
WORD_WITH_LEET = re.compile(
    r"\b(?=[a-z0-9@$]*[a-z])(?=[a-z0-9@$]*[0-9@$])[a-z0-9@$]{3,}\b", re.IGNORECASE
)


def deleet(text: str) -> str:
    """Only words that mix letters with look-alike digits change ("h1de"), so "3 cartons" and
    "$40" stay as they are."""
    return WORD_WITH_LEET.sub(lambda m: m.group(0).translate(LEET), text)


@lru_cache(maxsize=1)
def get_guard() -> Guard:
    return Guard()
