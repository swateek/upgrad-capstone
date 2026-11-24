"""Search queries and topic scopes built by code, never by the model (plan §4.4, small-model
log #27, #30).

A query is the user's question plus the names of the rules the step relies on, e.g.
"... What do I owe?\nflat rate duty; excise general rates". A rule's topic scope is the set of
topics of the sources its signed-off cites point to (R7 -> rates, R4 -> sanctions + declaring,
a state flag -> state); the topic filter keeps only chunks from sources with those topics.
The retrieval experiment (eval/retrieval.py) measures exactly these functions.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from customs.tools.tables import Tables

_STATE = re.compile(r"^[A-Z]{2}$")


def rule_key(claim: str) -> str:
    """'R9 which_exemption' -> 'R9'; 'CA arrival-state flag' -> 'CA'."""
    return claim.split()[0]


def _cites(tables: Tables, key: str) -> list[str]:
    if _STATE.match(key):
        return list(tables.states[key]["cites"])
    return tables.cites(key)


def search_terms(tables: Tables, key: str) -> str:
    """Words for one rule: its table name ('flat rate duty'), or the state's flag heading."""
    if _STATE.match(key):
        name = tables.states[key]["flag"].split(":", 1)[0].strip()
        return f"{name} state law bringing alcohol into the state"
    return tables.rules[key]["name"].replace("_", " ")


def build_query(question: str, tables: Tables, keys: Iterable[str] = ()) -> str:
    terms = [search_terms(tables, k) for k in dict.fromkeys(keys)]
    return question.strip() + ("\n" + "; ".join(terms) if terms else "")


def scope(tables: Tables, keys: Iterable[str], source_topics: Mapping[str, str]) -> set[str]:
    """Source ids allowed by the topic filter for these rules (empty set = no filter)."""
    topics = {
        source_topics[c.split(":", 1)[0]]
        for k in keys
        for c in _cites(tables, k)
        if c.split(":", 1)[0] in source_topics
    }
    return {s for s, t in source_topics.items() if t in topics}
