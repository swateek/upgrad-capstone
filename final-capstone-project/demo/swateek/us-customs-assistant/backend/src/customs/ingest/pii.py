"""Scrub personal identifiers before anything is chunked, indexed or traced.

US patterns for this app: email, US phone numbers, Social Security numbers, US passport-style
numbers next to the word "passport". The same scrubber masks traces (customs.observability).
"""

from __future__ import annotations

import re
from collections import Counter

PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"),
    "SSN": re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
    "PASSPORT": re.compile(r"(?i)\bpassport(?:\s+(?:no\.?|number|#))?[\s:#]*([A-Z]?\d{8,9})\b"),
    "PHONE": re.compile(
        r"(?<![\w-])(?:\+?1[ .-]?)?\(?[2-9]\d{2}\)?[ .-]?[2-9]\d{2}[ .-]?\d{4}(?![\w-])"
    ),
}


def scrub(text: str) -> tuple[str, Counter[str]]:
    found: Counter[str] = Counter()
    for label, pattern in PATTERNS.items():
        text, n = pattern.subn(f"[REDACTED-{label}]", text)
        if n:
            found[label] += n
    return text, found
