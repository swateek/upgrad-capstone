"""Deterministic scoring against the gold (SPEC §10). No model is used to score.

A turn is correct when its outcome equals gold and, for answered turns, the kind equals gold, the
amount owed is within $0.01, and every gold citation claim is satisfied by at least one cited
source. Citations may be clause ids ("cfr19_p148:148.33(d)", what the agent cites) or free text
("19 CFR 148.33", what a bare model writes); free text is matched at section level against the
corpus citation strings. A cited regulation that matches nothing in the corpus is "invented".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from customs.config import get_settings

STRUCTURED = re.compile(
    r"(\d+\s*cfr\s*\d+\.\d+[a-z]?)|(\d+\s*usc\s*\d+[a-z]?)|(ofac\s*faq\s*\d+)|(\d{4}\.\d{2}\.\d{2})"
    r"|(general\s*note\s*\d+)"
)


def norm(text: str) -> str:
    t = text.lower().replace("§", " ").replace("u.s.c.", "usc").replace("c.f.r.", "cfr")
    t = re.sub(r"\bsections?\b|\bsec\.", " ", t)
    t = re.sub(r"\bhtsus?\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def keys(text: str) -> set[str]:
    """Section-level keys in a citation text: '19 cfr 148.33', '26 usc 5001', 'ofac faq 720'."""
    return {re.sub(r"\s+", " ", "".join(m)).strip() for m in STRUCTURED.findall(norm(text))}


@dataclass
class Corpus:
    by_id: dict[str, str]  # clause id -> citation text
    keys_by_id: dict[str, set[str]]
    all_keys: set[str]


@lru_cache(maxsize=2)
def load_corpus(path: Path | None = None) -> Corpus:
    p = path or get_settings().data_dir / "chunks" / "documents.jsonl"
    by_id = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line:
            d = json.loads(line)
            by_id[d["doc_id"]] = d["citation"]
    keys_by_id = {k: keys(v) for k, v in by_id.items()}
    return Corpus(by_id, keys_by_id, set().union(*keys_by_id.values()))


def satisfies(cited: list[str], acceptable: list[str], corpus: Corpus) -> bool:
    if any(c in acceptable for c in cited):
        return True
    want = set().union(*(corpus.keys_by_id.get(a, set()) for a in acceptable))
    page_titles = {norm(corpus.by_id[a]).split(" — ")[0] for a in acceptable if a in corpus.by_id}
    for c in cited:
        if keys(c) & want:
            return True
        nc = norm(c)
        if any(t and len(t) > 12 and t in nc for t in page_titles):  # web-page citations
            return True
    return False


def invented(cited: list[str], corpus: Corpus) -> list[str]:
    """Free-text citations of a regulation section that does not exist in the corpus."""
    out = []
    for c in cited:
        if c in corpus.by_id:
            continue
        k = keys(c)
        if k and not (k & corpus.all_keys):
            out.append(c)
    return out


def to_dec(x) -> Decimal | None:
    if x is None or x == "":
        return None
    try:
        return Decimal(str(x).replace("$", "").replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


@dataclass
class TurnScore:
    outcome_ok: bool
    kind_ok: bool | None = None
    owe_ok: bool | None = None
    cite_ok: bool | None = None
    claims_met: int = 0
    claims: int = 0
    invented: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)

    @property
    def correct(self) -> bool:
        return self.outcome_ok and all(
            x is not False for x in (self.kind_ok, self.owe_ok, self.cite_ok)
        )


def score_turn(pred: dict, gold: dict, corpus: Corpus | None = None) -> TurnScore:
    """pred: {outcome, kind, owe_usd, citations[list of str]} (any missing key counts as wrong)."""
    corpus = corpus or load_corpus()
    s = TurnScore(outcome_ok=pred.get("outcome") == gold["outcome"])
    cited = [str(c) for c in pred.get("citations") or []]
    s.invented = invented(cited, corpus)
    if not s.outcome_ok:
        g, p = gold["outcome"], pred.get("outcome")
        s.labels.append(
            {
                ("clarify", "answered"): "no_clarify",
                ("answered", "clarify"): "unnecessary_clarify",
                ("refused", "answered"): "refusal_miss",
                ("out_of_scope", "answered"): "scope_miss",
                ("escalated", "answered"): "escalation_miss",
            }.get((g, p), f"wrong_outcome:{g}->{p}")
        )
    if gold["outcome"] == "answered":
        s.kind_ok = pred.get("kind") == gold["bottom_line"]["kind"]
        g_owe, p_owe = to_dec(gold["bottom_line"].get("owe_usd")), to_dec(pred.get("owe_usd"))
        s.owe_ok = g_owe is None or (p_owe is not None and abs(p_owe - g_owe) <= Decimal("0.01"))
        claims = gold.get("citations", [])
        s.claims = len(claims)
        s.claims_met = sum(satisfies(cited, c["acceptable"], corpus) for c in claims)
        s.cite_ok = s.claims_met == s.claims
        if s.outcome_ok:
            if not s.kind_ok:
                s.labels.append("wrong_kind")
            if not s.owe_ok:
                s.labels.append("wrong_amount")
            if not s.cite_ok:
                s.labels.append("missing_citation")
    if s.invented:
        s.labels.append("invented_citation")
    return s


# --- extraction (intake) -------------------------------------------------------------------------

PROFILE_FIELDS = [
    "age",
    "trip_hours",
    "arrived_directly_from",
    "exemption_used_last_30_days",
    "arrival_state",
]
LINE_FIELDS = ["item", "quantity", "container_ml", "abv", "value_usd", "origin"]


def _trip_bucket(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return ">=48" if float(v) >= 48 else "<48"


def _eq(field_name: str, a, b) -> bool:
    if field_name == "trip_hours":
        return _trip_bucket(a) == _trip_bucket(b)
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        try:
            return abs(float(a) - float(b)) < 1e-6
        except (TypeError, ValueError):
            return False
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().casefold() == b.strip().casefold()
    return a == b


def score_extraction(pred: dict, gold: dict) -> dict:
    """Field accuracy of an intake against the gold facts. Fields gold leaves unset are not
    scored, except that a value invented for an unset profile field counts as `invented`."""
    total = right = 0
    invented_fields = 0
    gp, pp = gold.get("profile", {}), pred.get("profile", {}) or {}
    for f in PROFILE_FIELDS:
        if f in gp:
            total += 1
            right += _eq(f, pp.get(f), gp[f])
        elif pp.get(f) is not None:
            invented_fields += 1
    gl, pl = gold.get("basket", []), pred.get("basket", []) or []
    total += 1
    right += len(gl) == len(pl)
    for i, g in enumerate(gl):
        p = pl[i] if i < len(pl) else {}
        for f in LINE_FIELDS:
            if g.get(f) is not None:
                total += 1
                right += _eq(f, p.get(f), g[f])
    return {"fields": total, "correct": right, "invented": invented_fields}
