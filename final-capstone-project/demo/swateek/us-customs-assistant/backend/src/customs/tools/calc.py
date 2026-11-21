"""The calculators (SPEC §5), in the SPEC's order. Every limit, rate and list comes from the
signed-off tables (customs.tools.tables); money is Decimal; each duty and excise line is rounded
half-up to the cent, then summed.

    case = new_case(profile, basket)
    step_normalise(case); step_restrictions(case); step_exemption(case)
    step_allowance(case); step_duty_excise(case); step_flags(case)
    assessment = finish(case)          # or simply: assess(profile, basket)

The executor tools (customs.tools.registry) each run one step on a shared Case, so the planner
can order and skip them; assess() runs them all (the code router and the tests).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from customs.tools.models import Assessment, Figure, Line, NLine, Profile
from customs.tools.tables import D, Tables, load_tables

CENT = Decimal("0.01")
ZERO = Decimal(0)


def cents(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(x: Decimal | int) -> str:
    """Whole numbers without a decimal point ("1000"), others as plain decimals ("354.882")."""
    x = Decimal(x)
    if x == x.to_integral_value():
        return str(int(x))
    return format(x.normalize(), "f")


def fmt_usd(x: Decimal) -> str:
    return str(cents(x))


@dataclass
class LineCalc:
    exempt_ml: Decimal = ZERO
    dutiable_ml: Decimal = ZERO
    exempt_sticks: int = 0
    excess_sticks: int = 0
    duty_rate: Decimal | None = None
    dutiable_value: Decimal | None = None  # unrounded, pro rata
    duty: Decimal | None = None
    excise: Decimal | None = None
    fta: bool = False


@dataclass
class Case:
    profile: Profile
    basket: list[Line]
    t: Tables
    lines: list[NLine] = field(default_factory=list)
    calc: dict[int, LineCalc] = field(default_factory=dict)
    scope: str | None = None  # whole-question scope note (non_resident, insular, crew, shipped)
    exemption: int | None = None
    alcohol_allowance_ml: Decimal | None = None
    tobacco_allowance: dict[str, int] = field(default_factory=dict)
    all_or_nothing_triggered: bool = False
    escalation: str | None = None
    rule_refs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    defaults_used: list[str] = field(default_factory=list)
    done: set[str] = field(default_factory=set)

    # --- helpers ------------------------------------------------------------------------------
    def ref(self, r: str) -> None:
        if r not in self.rule_refs:
            self.rule_refs.append(r)

    def note(self, n: str) -> None:
        if n not in self.notes:
            self.notes.append(n)

    @property
    def admissible(self) -> list[NLine]:
        return [nl for nl in self.lines if nl.admissible and (nl.is_alcohol or nl.is_tobacco)]

    @property
    def alcohol(self) -> list[NLine]:
        return [nl for nl in self.admissible if nl.is_alcohol]

    @property
    def tobacco(self) -> list[NLine]:
        return [nl for nl in self.admissible if nl.is_tobacco]

    @property
    def under_21(self) -> bool:
        return (
            self.profile.age is not None
            and self.profile.age < self.t.params("R3")["alcohol_min_age"]
        )


def new_case(profile: Profile, basket: list[Line], tables: Tables | None = None) -> Case:
    return Case(profile=profile, basket=basket, t=tables or load_tables())


# --- step 0: units ------------------------------------------------------------------------------

UNIT_VOLUMES = {  # unit -> key in units.yaml volumes_ml, or a literal ml value
    "fifth": "fifth",
    "magnum": "magnum",
    "half_bottle": "half_bottle",
    "pint": "pint_us",
    "can": "can_12oz",
}


def step_normalise(case: Case) -> None:
    t = case.t
    vols = t.units["volumes_ml"]
    counts = t.units["counts"]
    case.lines = []
    for i, line in enumerate(case.basket, start=1):
        nl = NLine(index=i, line=line)
        if line.item in ("wine", "sparkling_wine", "beer", "spirits", "liqueur", "hard_cider"):
            if line.quantity is None:
                nl.status = "unknown_quantity"
            else:
                q = D(line.quantity)
                unit = (line.unit or "").lower()
                if unit == "ml":
                    nl.volume_ml = q
                elif unit in ("l", "litre", "liter"):
                    nl.volume_ml = q * 1000
                else:
                    if line.container_ml is not None:
                        size = D(line.container_ml)
                    elif unit in UNIT_VOLUMES:
                        size = D(vols[UNIT_VOLUMES[unit]])
                    else:  # bottle or unknown container: a standard 750 ml bottle
                        size = D(vols["bottle_spirits" if line.item != "wine" else "bottle_wine"])
                        nl.container_defaulted = True
                        case.defaults_used.append(f"line {i}: 750 ml bottle assumed")
                    nl.volume_ml = q * size
            if line.abv is not None:
                nl.abv = D(line.abv)
            else:
                nl.abv = t.default_abv(line.item)
                nl.abv_defaulted = nl.abv is not None
                if nl.abv_defaulted:
                    case.defaults_used.append(f"line {i}: {fmt(nl.abv)}% ABV assumed")
        elif line.item in ("cigarettes", "cigars"):
            if line.quantity is None:
                nl.status = "unknown_quantity"
            else:
                unit = (line.unit or "").lower()
                per = {
                    "pack": counts["cigarettes_per_pack"],
                    "carton": counts["cigarettes_per_carton"],
                }.get(unit, 1)
                if unit == "box" and counts.get("cigars_per_box") is None:
                    nl.status = "unknown_quantity"
                else:
                    nl.sticks = int(D(line.quantity) * per)
        else:
            nl.status = "out_of_scope"
        case.lines.append(nl)
    case.done.add("normalise")


# --- step 1: restrictions (R4, R12, Russia scope, other goods, profile scope) -------------------


def step_restrictions(case: Case) -> None:
    t, p = case.t, case.profile
    if not p.us_resident:
        case.scope = "non_resident"
    elif p.arrived_directly_from in t.insular:
        case.scope = "insular"
    elif p.crew:
        case.scope = "crew"
    elif p.shipped:
        case.scope = "shipped"
    for nl in case.lines:
        line = nl.line
        if nl.status == "out_of_scope":
            case.note(f"scope_note:{line.other_kind}")
            continue
        origin = (line.origin or "").upper() or None
        brand_ambiguous = bool(line.brand) and line.brand.casefold() in t.ambiguous_brands
        if origin == "CU":
            nl.status = "prohibited"
            nl.prohibited_where = "acquired_in_cuba" if line.bought_in == "CU" else "third_country"
        elif origin == "RU" and nl.is_alcohol:
            nl.status = "russian_scope"
            case.note("scope_note:russian")
        elif brand_ambiguous and origin in (None, "UNKNOWN"):
            # Decision E: asked once already (clarify); still unknown -> possibly Cuban
            nl.status = "possibly_cuban"
    if p.travelling_as_family:
        case.note("scope_note:family")
    case.done.add("restrictions")


# --- step 2: which exemption (R9) ---------------------------------------------------------------


def step_exemption(case: Case) -> None:
    p, r9 = case.profile, case.t.params("R9")
    from_mexico = p.arrived_directly_from in set(r9["no_min_hours_from"])
    qualifies = (bool(p.long_trip) or from_mexico) and not p.exemption_used_last_30_days
    case.exemption = 800 if qualifies else 200
    if case.admissible:
        case.ref("R9")
        if case.exemption == 200:
            case.ref("R1")
    case.done.add("exemption")


# --- step 3: allowance (R1, R2, R3, R5, R11) -----------------------------------------------------


def excise_per_litre(nl: NLine, t: Tables) -> Decimal:
    """Federal excise for one litre of this line's product (R8)."""
    classes = t.excise_classes
    gal_per_l = 1 / t.litres_per_gallon
    abv = nl.abv if nl.abv is not None else ZERO
    item = nl.line.item
    if item in ("spirits", "liqueur") or abv > 24:
        c = classes["distilled_spirits"]
        return gal_per_l * abv * t.units["proof_per_abv_percent"] / 100 * c.rate
    if item == "beer":
        return gal_per_l / t.gallons_per_barrel * classes["beer"].rate
    if item == "sparkling_wine":
        return gal_per_l * classes["sparkling_wine"].rate
    if item == "hard_cider":
        return gal_per_l * classes["hard_cider"].rate
    for name in ("still_wine_le_16", "still_wine_16_21", "still_wine_21_24"):
        c = classes[name]
        lo = c.min_abv_exclusive if c.min_abv_exclusive is not None else Decimal(-1)
        if lo < abv <= c.max_abv:
            return gal_per_l * c.rate
    raise ValueError(f"no wine band for {abv}% ABV")


def step_allowance(case: Case) -> None:
    t = case.t
    alcohol, tobacco = case.alcohol, case.tobacco
    case.calc = {nl.index: LineCalc() for nl in case.admissible}
    if case.exemption == 200:
        r1 = t.params("R1")
        lim = r1["limits"]
        cig = sum(nl.sticks or 0 for nl in tobacco if nl.line.item == "cigarettes")
        cgr = sum(nl.sticks or 0 for nl in tobacco if nl.line.item == "cigars")
        ml = sum((nl.volume_ml or ZERO for nl in alcohol), ZERO)
        value = sum((D(nl.line.value_usd) for nl in case.admissible if nl.line.value_usd), ZERO)
        within = (
            cig <= lim["cigarettes"]
            and cgr <= lim["cigars"]
            and ml <= lim["alcohol_ml"]
            and value <= r1["value_limit_usd"]
            and not (case.under_21 and case.admissible)
        )
        case.all_or_nothing_triggered = not within
        case.alcohol_allowance_ml = D(lim["alcohol_ml"])
        for nl in case.admissible:
            c = case.calc[nl.index]
            if nl.is_alcohol:
                c.exempt_ml = nl.volume_ml if within else ZERO
                c.dutiable_ml = ZERO if within else nl.volume_ml
            else:
                c.exempt_sticks = nl.sticks if within else 0
                c.excess_sticks = 0 if within else nl.sticks
        if tobacco and not within:
            case.ref("R5")
    else:
        # alcohol allowance: 1 L, or 2 L from a Caribbean Basin country (R2); none under 21 (R3)
        if case.under_21:
            allow = ZERO
        else:
            r2 = t.params("R2")
            benef = sum(
                (nl.volume_ml for nl in alcohol if (nl.line.origin or "") in t.cbi_countries),
                ZERO,
            )
            from_cbi = case.profile.arrived_directly_from in t.cbi_countries
            allow = (
                D(r2["litres"]) * 1000
                if from_cbi and benef >= D(r2["min_beneficiary_product_litres"]) * 1000
                else D(t.params("R9")["alcohol_litres"]) * 1000
            )
            if from_cbi and alcohol:
                case.ref("R2")
        case.alcohol_allowance_ml = allow

        # R11: highest (3% of value per litre + excise per litre) first; stable by line order
        def cost_per_litre(nl: NLine) -> Decimal:
            litres = nl.volume_ml / 1000
            value = D(nl.line.value_usd) if nl.line.value_usd is not None else ZERO
            return t.flat_rate * value / litres + excise_per_litre(nl, t)

        left = allow
        for nl in sorted(alcohol, key=lambda n: -cost_per_litre(n)):
            c = case.calc[nl.index]
            c.exempt_ml = min(left, nl.volume_ml)
            c.dutiable_ml = nl.volume_ml - c.exempt_ml
            left -= c.exempt_ml
        if len(alcohol) >= 2 and allow > 0 and any(case.calc[n.index].dutiable_ml for n in alcohol):
            case.ref("R11")

        # tobacco: 200 cigarettes / 100 cigars (R5); none under 21 (Decision B)
        r5 = t.params("R5")["allowance"]
        min_age_tob = t.params("R3")["tobacco_min_age"]
        no_tob = case.profile.age is not None and case.profile.age < min_age_tob
        left_t = {k: (0 if no_tob else int(v)) for k, v in r5.items()}
        case.tobacco_allowance = dict(left_t)
        for nl in tobacco:
            c = case.calc[nl.index]
            kind = nl.line.item
            c.exempt_sticks = min(left_t[kind], nl.sticks)
            c.excess_sticks = nl.sticks - c.exempt_sticks
            left_t[kind] -= c.exempt_sticks
        if tobacco:
            case.ref("R5")
    if case.under_21 and case.admissible:
        case.ref("R3")
    if any(nl.line.us_made_export_labelled for nl in tobacco):
        case.ref("R6")
    case.done.add("allowance")


# --- steps 5-7: duty and excise on dutiable alcohol (R7, R8) --------------------------------------


def duty_rate_for(nl: NLine, t: Tables) -> tuple[Decimal, bool]:
    """(rate, fta) for a dutiable line: partner product 0 (Decision C), Column 2 4%, else 3%."""
    origin = (nl.line.origin or "").upper()
    if t.params("R7")["fta_free"] and origin in t.partner_programs:
        return ZERO, True
    if origin in t.column2:
        return t.column2_rate, False
    return t.flat_rate, False


def step_duty_excise(case: Case) -> None:
    t = case.t
    for nl in case.alcohol:
        c = case.calc[nl.index]
        if not c.dutiable_ml:
            continue
        c.duty_rate, c.fta = duty_rate_for(nl, t)
        if nl.line.value_usd is not None:
            c.dutiable_value = D(nl.line.value_usd) * c.dutiable_ml / nl.volume_ml
            c.duty = cents(c.duty_rate * c.dutiable_value)
        c.excise = cents(c.dutiable_ml / 1000 * excise_per_litre(nl, t))
        case.ref("R7")
        case.ref("R8")
    case.done.add("duty_excise")


# --- step 8: flags and caps (R10, R11 basket cap, R7 cap, state) -----------------------------------


def total_alcohol_ml(case: Case) -> Decimal:
    return sum((nl.volume_ml or ZERO for nl in case.alcohol), ZERO)


def step_caps(case: Case) -> None:
    """Escalation caps, checked before money is shown (SPEC §5 step 8, §12)."""
    t = case.t
    if total_alcohol_ml(case) > D(t.params("R10")["flag_litres_per_traveller"]) * 1000:
        case.escalation = "large_quantity"
        case.ref("R10")
        case.note("large_quantity")
        return
    basket_value = sum(
        (D(nl.line.value_usd) for nl in case.admissible if nl.line.value_usd is not None), ZERO
    )
    if basket_value > D(t.params("R11")["escalate_if_basket_value_over_usd"]):
        case.escalation = "basket_over_800"
        return
    dutiable_value = sum(
        (c.dutiable_value for c in case.calc.values() if c.dutiable_value is not None), ZERO
    )
    if dutiable_value > D(t.params("R7")["cap_usd"]):
        case.escalation = "dutiable_over_1000"


def step_flags(case: Case) -> None:
    t = case.t
    for nl in case.lines:
        if nl.status == "prohibited":
            case.ref(f"R4:{nl.prohibited_where}")
            case.note("cuban_prohibited")
        elif nl.status == "possibly_cuban":
            case.ref("R12")
            case.ref("R4:third_country")
            case.note("possibly_cuban_declare")
    if any(c.excess_sticks for c in case.calc.values()):
        case.note("seizure_risk")
    if any(
        nl.index in case.calc
        and case.calc[nl.index].excess_sticks
        and nl.line.us_made_export_labelled
        for nl in case.tobacco
    ):
        case.note("us_export_labelled_relinquish")
    if any(c.fta for c in case.calc.values()):
        case.note("fta_caveat")
    if any(c.dutiable_ml and c.dutiable_value is None for c in case.calc.values()):
        case.note("value_unknown_duty_note")
    if case.alcohol:
        state = (case.profile.arrival_state or "").upper()
        if state in t.states:
            case.ref(f"state:{state}")
            case.note(f"state_flag:{state}")
        else:
            case.note("generic_state_note")
    case.done.add("flags")


# --- finish: figures, kind, outcome ------------------------------------------------------------


def _figures(case: Case) -> list[Figure]:
    figs: list[Figure] = []

    def add(name: str, value: str, unit: str) -> None:
        figs.append(Figure(name=name, value=value, unit=unit))

    if not case.admissible or case.exemption is None:
        return figs  # nothing assessable, or the steps did not run (the audit reports that)
    add("exemption_usd", str(case.exemption), "usd")
    if case.alcohol and case.alcohol_allowance_ml is not None:
        add("alcohol_allowance_ml", fmt(case.alcohol_allowance_ml), "ml")
    if case.escalation:
        return figs
    duty_total = excise_total = ZERO
    any_dutiable = False
    all_values_known = True
    for nl in case.admissible:
        c = case.calc.get(nl.index)
        if c is None:
            continue
        i = nl.index
        if nl.is_alcohol:
            add(f"exempt_ml_{i}", fmt(c.exempt_ml), "ml")
            add(f"dutiable_ml_{i}", fmt(c.dutiable_ml), "ml")
            if c.dutiable_ml and c.excise is not None:  # money only once duty/excise ran
                any_dutiable = True
                if c.dutiable_value is not None:
                    add(f"dutiable_value_usd_{i}", fmt_usd(c.dutiable_value), "usd")
                add(f"duty_rate_{i}", fmt(c.duty_rate), "rate")
                if c.duty is not None:
                    add(f"duty_usd_{i}", fmt_usd(c.duty), "usd")
                    duty_total += c.duty
                else:
                    all_values_known = False
                add(f"excise_usd_{i}", fmt_usd(c.excise), "usd")
                excise_total += c.excise
        else:
            add(f"exempt_sticks_{i}", str(c.exempt_sticks), "sticks")
            add(f"excess_sticks_{i}", str(c.excess_sticks), "sticks")
    if any_dutiable:
        if all_values_known:
            add("duty_total_usd", fmt_usd(duty_total), "usd")
        add("excise_total_usd", fmt_usd(excise_total), "usd")
        if all_values_known:
            add("total_owed_usd", fmt_usd(duty_total + excise_total), "usd")
    return figs


def finish(case: Case) -> Assessment:
    if case.scope:
        return Assessment(
            outcome="out_of_scope", kind="out_of_scope", notes=[f"scope_note:{case.scope}"]
        )
    has_prohibited = any(nl.status in ("prohibited", "possibly_cuban") for nl in case.lines)
    if not case.admissible and not has_prohibited:
        notes = [n for n in case.notes if n.startswith("scope_note:")] or ["scope_note:other_goods"]
        return Assessment(outcome="out_of_scope", kind="out_of_scope", notes=notes)
    figures = _figures(case)
    if case.escalation:
        return Assessment(
            outcome="escalated",
            kind="escalated",
            exemption_usd=case.exemption if case.admissible else None,
            figures=figures,
            rule_refs=[r for r in case.rule_refs if r == "R10"] or list(case.rule_refs),
            notes=["disclaimer", *(n for n in case.notes if n == "large_quantity")],
            lines=case.lines,
            escalation_reason=case.escalation,
            defaults_used=case.defaults_used,
        )
    duty = sum((c.duty for c in case.calc.values() if c.duty is not None), ZERO)
    excise = sum((c.excise for c in case.calc.values() if c.excise is not None), ZERO)
    owed = duty + excise
    has_seizure = any(c.excess_sticks for c in case.calc.values())
    flags = [owed > 0, has_prohibited, has_seizure]
    if sum(flags) >= 2:
        kind = "mixed"
    elif owed > 0:
        kind = "owe"
    elif has_prohibited:
        kind = "prohibited"
    elif has_seizure:
        kind = "seizure_risk"
    else:
        kind = "nothing_owed"
    return Assessment(
        outcome="answered",
        kind=kind,
        owe_usd=cents(owed),
        exemption_usd=case.exemption if case.admissible else None,
        figures=figures,
        rule_refs=list(case.rule_refs),
        notes=["disclaimer", *case.notes],
        lines=case.lines,
        defaults_used=case.defaults_used,
    )


def assess(profile: Profile, basket: list[Line], tables: Tables | None = None) -> Assessment:
    """Run every step in the SPEC's order (the code router's plan)."""
    case = new_case(profile, basket, tables)
    step_normalise(case)
    step_restrictions(case)
    if case.scope:
        return finish(case)
    step_exemption(case)
    step_allowance(case)
    step_duty_excise(case)
    step_caps(case)
    step_flags(case)
    return finish(case)
