"""Refusal pre-check: match a request against the domain's refusal rules before the planner runs.

Domain files (paths in domain.yaml `refusals`):
  rules     refusals.yaml          rule id -> trigger description + fixed wording; banned phrases
  patterns  refusal_patterns.yaml  rule id -> regexes that detect a request to do that thing
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml

from copilot.domains.loader import DomainConfig


@dataclass(frozen=True)
class RefusalHit:
    rule_id: str
    wording: str
    matched: str


class RefusalPolicy:
    def __init__(self, domain: DomainConfig) -> None:
        cfg = domain.refusals
        rules = (
            yaml.safe_load(domain.path(cfg["rules"]).read_text(encoding="utf-8"))
            if "rules" in cfg
            else {}
        )
        pats = (
            yaml.safe_load(domain.path(cfg["patterns"]).read_text(encoding="utf-8"))
            if "patterns" in cfg
            else {}
        )
        self.wording = {r["id"]: " ".join(r["wording"].split()) for r in rules.get("rules", [])}
        self.patterns = {
            rid: [re.compile(p, re.IGNORECASE) for p in spec.get("patterns", [])]
            for rid, spec in (pats.get("rules") or {}).items()
        }
        self.banned: dict[str, list[str]] = rules.get("banned_phrases", {}) or {}

    def check(self, text: str) -> list[RefusalHit]:
        hits = []
        for rid, regexes in self.patterns.items():
            for rx in regexes:
                m = rx.search(text)
                if m:
                    hits.append(RefusalHit(rid, self.wording.get(rid, ""), m.group(0)))
                    break
        return hits

    def banned_in(self, answer: str, jobs: list[str]) -> list[str]:
        low = answer.lower()
        found = []
        for key in ["all_jobs", *jobs]:
            for phrase in self.banned.get(key, []):
                if phrase.lower() in low:
                    found.append(phrase)
        return found

    def as_dict(self) -> dict[str, Any]:
        return {"rules": sorted(self.patterns), "banned": self.banned}
