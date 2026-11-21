"""Scrub personal identifiers before anything is chunked or indexed."""

from __future__ import annotations

import re
from collections import Counter

PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"),
    "PAN": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "AADHAAR": re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b"),
    "PHONE": re.compile(r"(?<!\d)(?:\+91[ -]?|0)?[6-9]\d{9}(?!\d)"),
}


def scrub(text: str) -> tuple[str, Counter[str]]:
    found: Counter[str] = Counter()
    for label, pattern in PATTERNS.items():
        text, n = pattern.subn(f"[REDACTED-{label}]", text)
        if n:
            found[label] += n
    return text, found
