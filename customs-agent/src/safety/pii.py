"""PII masking for anything written to logs or traces (mentor plan: PII masking in logs).

Travellers may type an email, a phone number, a passport or card number, or their name. None of it
is needed to assess duty, so it is masked before a question or answer leaves the process (Langfuse,
logs/trace.jsonl). Patterns are narrow on purpose: prices, volumes, ages and dates are not PII and
must survive ("$1,000", "750 ml", "I'm 34").
"""

from __future__ import annotations

import re
from typing import Any

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("[email]", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("[card]", re.compile(r"\b(?:\d{4}[ -]){3}\d{1,4}\b|\b\d{15,16}\b")),
    (
        "[phone]",
        re.compile(
            r"(?<![\w$])(?:\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"
        ),
    ),
    (
        "[passport]",
        re.compile(
            r"\b(?:passport|pp)(?:\s+(?:no\.?|number|#))?\s*[:#]?\s*[A-Z0-9]{6,9}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "[name]",
        re.compile(r"\b(?i:my name is|name:)\s+[A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+)?"),
    ),
]


def mask_text(text: str) -> str:
    for token, pat in PATTERNS:
        text = pat.sub(token, text)
    return text


def mask(obj: Any) -> Any:
    """Mask every string inside a JSON-like value."""
    if isinstance(obj, str):
        return mask_text(obj)
    if isinstance(obj, dict):
        return {k: mask(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [mask(v) for v in obj]
    return obj
