"""Which answer-changing facts are missing (SPEC §6, pack/rules/facts.yaml).

A fact is asked for only when it is missing AND changes the answer. Several are bundled into ONE
short question; the arrival state is only ever added to a question that asks something else.
Values and origins matter only for lines that are dutiable on the normal branch (missing age
taken as 21+, missing 30-day use as "not used", missing trip length as 48 hours or more).
"""

from __future__ import annotations

from customs.tools.calc import (
    new_case,
    step_allowance,
    step_exemption,
    step_normalise,
    step_restrictions,
)
from customs.tools.models import Line, Profile
from customs.tools.tables import Tables, load_tables

AGE = "age_21_plus"
TRIP = "trip_hours_or_arrived_from_mexico"
USED = "exemption_used_last_30_days"
ORIGIN = "origin_country_of_line"
VALUE = "value_usd_of_line"
STATE = "arrival_state"

# The wording the clarify node uses (one short question, SPEC §6).
QUESTIONS = {
    AGE: "Are you 21 or older?",
    TRIP: "How long were you away (or did you come straight back from Mexico)?",
    USED: "Have you used your duty-free exemption in the last 30 days?",
    ORIGIN: "Where was it made?",
    VALUE: "Roughly what did it cost?",
    STATE: "Which US state are you arriving in?",
}


def missing_facts(profile: Profile, basket: list[Line], tables: Tables | None = None) -> list[str]:
    t = tables or load_tables()
    case = new_case(profile, basket, t)
    step_normalise(case)
    step_restrictions(case)
    if case.scope:
        return []
    ambiguous = [
        nl
        for nl in case.lines
        if nl.status == "possibly_cuban" and nl.line.origin is None  # not asked yet
    ]
    if not case.admissible and not ambiguous:
        return []  # nothing assessable (all Cuban, out of scope...): no fact changes the answer

    fields: list[str] = []
    p = profile
    mexico = set(t.params("R9")["no_min_hours_from"])
    if case.admissible:
        if p.age is None:
            fields.append(AGE)
        # facts.yaml: the trip fact is "trip_hours_or_arrived_from_mexico". A trip under 48 hours
        # still gets $800 straight from Mexico (R9), so it is missing when the arrival country
        # is unknown and nothing said rules Mexico out (live smoke test 18 Nov: a Tijuana day
        # trip with no arrival country got the $200 exemption).
        visited = set(p.countries_visited)
        mexico_open = p.arrived_directly_from is None and not (visited and not visited & mexico)
        if p.arrived_directly_from not in mexico and (
            p.long_trip is None or (p.long_trip is False and mexico_open)
        ):
            fields.append(TRIP)
        if p.exemption_used_last_30_days is None:
            fields.append(USED)
    if ambiguous:
        fields.append(ORIGIN)

    # normal branch: which lines are dutiable if the missing person facts come out "normally"?
    normal = profile.model_copy(
        update={
            "age": p.age if p.age is not None else 30,
            "exemption_used_last_30_days": bool(p.exemption_used_last_30_days),
            "trip_hours": p.trip_hours if p.trip_hours is not None else ">=48",
        }
    )
    branch = new_case(normal, basket, t)
    step_normalise(branch)
    step_restrictions(branch)
    step_exemption(branch)
    step_allowance(branch)
    partners = set(t.partner_programs)
    for nl in branch.alcohol:
        c = branch.calc[nl.index]
        if not c.dutiable_ml:
            continue
        if nl.line.value_usd is None and VALUE not in fields:
            fields.append(VALUE)
        if nl.line.origin is None and ORIGIN not in fields:
            source = nl.line.bought_in
            if source in (None, "duty_free"):
                source = p.arrived_directly_from
            if source in partners:
                fields.append(ORIGIN)
    # a 2-litre Caribbean Basin claim depends on where the alcohol was made (R2)
    if (
        ORIGIN not in fields
        and branch.exemption == 800
        and p.arrived_directly_from in t.cbi_countries
        and any(nl.line.origin is None for nl in branch.alcohol)
        and sum(nl.volume_ml for nl in branch.alcohol) > 1000
    ):
        fields.append(ORIGIN)

    if fields and case.alcohol and not p.arrival_state:
        fields.append(STATE)
    return fields


def clarify_question(fields: list[str]) -> str:
    return " ".join(QUESTIONS[f] for f in fields)
