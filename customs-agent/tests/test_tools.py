"""Rule tests for the calculator tools, one behaviour per test, with the clause it comes from.

Numbers here are chosen for the tests; none is an eval scenario (CLAUDE.md rule 6).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.schemas import Amount, BasketLine, Duration, Profile
from src.tools import ToolError, lookup_state_rule, normalise_units
from src.tools.common import cents, dec, dollars, match
from src.tools.compute_duty_excise import duty_rate
from src.tools.lookup_state_rule import Args as SArgs
from src.tools.normalise_units import Args as NArgs
from tests._chain import run

ADULT = {
    "age": 40,
    "trip": Duration(value=7, unit="days"),
    "exemption_used_last_30_days": False,
}


def bottle(
    item="wine", type_="wine", n=1, ml=750, abv=12.0, price=20.0, origin="FR", **kw
) -> BasketLine:
    return BasketLine(
        item=item,
        category="alcohol",
        type=type_,
        quantity=Amount(value=n, unit="bottle"),
        size=Amount(value=ml, unit="ml"),
        abv=abv,
        unit_price_usd=price,
        origin=origin,
        **kw,
    )


def smokes(
    n=1, unit="carton", type_="cigarettes", price=40.0, origin="FR", **kw
) -> BasketLine:
    return BasketLine(
        item=type_,
        category="tobacco",
        type=type_,
        quantity=Amount(value=n, unit=unit),
        unit_price_usd=price,
        origin=origin,
        **kw,
    )


# ------------------------------------------------------------------ normalise_units


@pytest.mark.parametrize(
    ("qty", "size", "ml", "total_l"),
    [
        (
            Amount(value=2, unit="bottles"),
            Amount(value=70, unit="cl"),
            Decimal(700),
            Decimal("1.400"),
        ),
        (Amount(value=1, unit="fifth"), None, Decimal(750), Decimal("0.750")),
        (Amount(value=3, unit="miniatures"), None, Decimal(50), Decimal("0.150")),
        (
            Amount(value=1, unit="bottle"),
            Amount(value=1, unit="L"),
            Decimal(1000),
            Decimal("1.000"),
        ),
        (Amount(value=500, unit="ml"), None, Decimal(500), Decimal("0.500")),
        # quantity given as a volume of containers of a stated size: 2 litres of 1-litre bottles
        (
            Amount(value=2, unit="litre"),
            Amount(value=1, unit="litre"),
            Decimal(1000),
            Decimal("2.000"),
        ),
        # not a whole number of containers: one container of the stated volume, as before
        (
            Amount(value=2, unit="litre"),
            Amount(value=750, unit="ml"),
            Decimal(2000),
            Decimal("2.000"),
        ),
    ],
)
def test_normalise_alcohol_volumes(qty, size, ml, total_l) -> None:
    line = BasketLine(
        item="gin", category="alcohol", type="spirits", quantity=qty, size=size, abv=40
    )
    n = normalise_units(NArgs(basket=[line]))[0]
    assert (n.unit_ml, n.total_l) == (ml, total_l)
    assert n.units * n.unit_ml == total_l * 1000
    assert n.proof == Decimal(80)


@pytest.mark.parametrize(
    ("qty", "type_", "count"),
    [
        (Amount(value=2, unit="cartons"), "cigarettes", 400),
        (Amount(value=3, unit="packs"), "cigarettes", 60),
        (Amount(value=2, unit="box of 20"), "cigars", 40),
        (Amount(value=7, unit="cigars"), "cigars", 7),
    ],
)
def test_normalise_tobacco_counts(qty, type_, count) -> None:
    line = BasketLine(item=type_, category="tobacco", type=type_, quantity=qty)
    assert normalise_units(NArgs(basket=[line]))[0].count == count


def test_bottle_without_size_is_a_missing_fact() -> None:
    line = BasketLine(
        item="rum",
        category="alcohol",
        type="spirits",
        quantity=Amount(value=2, unit="bottle"),
        abv=40,
    )
    with pytest.raises(ToolError) as e:
        normalise_units(NArgs(basket=[line]))
    assert e.value.missing == ["size"]


@pytest.mark.parametrize(
    ("type_", "abv", "cls"),
    [
        ("wine", 14.5, "still_up_to_16_abv"),
        ("wine", 16.0, "still_up_to_16_abv"),
        ("wine", 18, "still_over_16_to_21_abv"),
        ("sparkling_wine", 11, "sparkling"),
        ("beer", 5, "beer"),
        ("spirits", 40, "spirits"),
    ],
)
def test_excise_class(type_, abv, cls) -> None:  # TTB tax-rate classes
    assert (
        normalise_units(NArgs(basket=[bottle(type_=type_, abv=abv)]))[0].excise_class
        == cls
    )


# ------------------------------------------------------------------ restrictions


def test_cuban_cigars_bought_anywhere_are_prohibited() -> (
    None
):  # 31 CFR 515.204, 515.585(d)
    r = run(
        Profile(**ADULT),
        [smokes(1, "box of 10", "cigars", origin="CU", bought_where="CA")],
    )
    assert r["bottom_line"] == ["prohibited"]


def test_russian_alcohol_escalates() -> (
    None
):  # rules.yaml russian_origin_alcohol (open)
    r = run(Profile(**ADULT), [bottle("vodka", "spirits", abv=40, origin="RU")])
    assert r == {"outcome": "escalated", "rule_id": "russian_origin_alcohol"}


def test_rum_of_unknown_origin_asks_for_origin() -> None:  # SPEC 5.2 stage 1
    r = run(Profile(**ADULT), [bottle("dark rum", "spirits", abv=40, origin=None)])
    assert r == {"outcome": "clarify", "missing": ["origin"]}


def test_gin_of_unknown_origin_does_not_ask_in_stage_1() -> None:
    r = run(Profile(**ADULT), [bottle("gin", "spirits", n=1, abv=40, origin=None)])
    assert r["outcome"] == "answered" and r["bottom_line"] == ["nothing_to_pay"]


def test_age_missing_is_asked() -> None:
    r = run(
        Profile(trip=Duration(value=7, unit="days"), exemption_used_last_30_days=False),
        [bottle()],
    )
    assert r == {"outcome": "clarify", "missing": ["age"]}


@pytest.mark.parametrize(
    ("n", "ml", "escalates"),
    [(12, 750, False), (13, 500, True), (6, 1500, False), (7, 1500, True)],
)
def test_commercial_quantity_threshold(
    n, ml, escalates
) -> None:  # SPEC 5.4: > 9 L or > 12 units
    r = run(Profile(**ADULT), [bottle(n=n, ml=ml, price=10)])
    assert (
        r["outcome"] == "escalated" and r.get("rule_id") == "commercial_quantity"
    ) == escalates


# ------------------------------------------------------------------ exemption


@pytest.mark.parametrize(
    ("trip", "arrival", "kind"),
    [
        (Duration(value=47, unit="hours"), None, "short_trip_200"),
        (Duration(value=48, unit="hours"), None, "standard_800"),
        (Duration(value=2, unit="days"), None, "standard_800"),
        (Duration(value=6, unit="hours"), "MX", "standard_800"),  # 148.35(a)
    ],
)
def test_exemption_by_trip(trip, arrival, kind) -> None:
    p = Profile(
        age=40,
        trip=trip,
        direct_arrival_from=arrival,
        exemption_used_last_30_days=False,
    )
    assert run(p, [bottle(ml=100, price=10)])["exemption"].kind == kind


def test_exemption_used_in_30_days_gives_200() -> None:  # 148.36
    p = Profile(
        age=40,
        trip=Duration(value=3, unit="weeks"),
        exemption_used_last_30_days=True,
        flat_rate_used_last_30_days=False,
    )
    assert run(p, [bottle(ml=100, price=10)])["exemption"].kind == "short_trip_200"


def test_insular_possession_is_out_of_scope() -> None:
    p = Profile(
        age=40,
        trip=Duration(value=5, unit="days"),
        direct_arrival_from="VI",
        exemption_used_last_30_days=False,
    )
    assert run(p, [bottle()])["outcome"] == "out_of_scope"


def test_unknown_trip_not_asked_when_basket_fits_200() -> None:  # SPEC 5.2
    p = Profile(age=40, exemption_used_last_30_days=False)
    r = run(p, [bottle(ml=100, price=10)])
    assert r["outcome"] == "answered" and r["bottom_line"] == ["nothing_to_pay"]


# ------------------------------------------------------------------ $200 all-or-nothing (148.51(b))

DAY = {
    "age": 40,
    "trip": Duration(value=10, unit="hours"),
    "direct_arrival_from": "CA",
    "exemption_used_last_30_days": False,
}


@pytest.mark.parametrize(
    ("ml", "price", "fails"),
    [(150, 10, False), (151, 10, True), (100, 200, False), (100, 200.01, True)],
)
def test_200_limits(ml, price, fails) -> None:
    r = run(Profile(**DAY), [bottle(ml=ml, price=price, origin="CA")])
    assert r["allowance"].all_or_nothing_failed == fails


def test_200_cigarette_limit_is_50() -> None:
    ok = run(Profile(**DAY), [smokes(50, "cigarettes", price=0.5, origin="CA")])
    over = run(Profile(**DAY), [smokes(51, "cigarettes", price=0.5, origin="CA")])
    assert ok["bottom_line"] == ["nothing_to_pay"] and over["bottom_line"] == [
        "declare_detention_risk"
    ]


def test_200_failure_makes_every_alcohol_line_dutiable() -> None:
    r = run(
        Profile(**DAY),
        [bottle(ml=100, price=5, origin="CA"), bottle(ml=100, price=5, origin="CA")],
    )
    assert [a.status for a in r["allowance"].lines] == ["dutiable", "dutiable"]


# ------------------------------------------------------------------ $800 alcohol and tobacco (148.33)


def test_spirits_take_the_free_litre_before_cheap_wine() -> (
    None
):  # 148.33(b), ranking per litre (SPEC 5.4)
    r = run(
        Profile(**ADULT),
        [
            bottle("wine", n=2, ml=750, abv=12, price=10),
            bottle("brandy", "spirits", ml=750, abv=40, price=30),
        ],
    )
    assert [a.exempt_l for a in r["allowance"].lines] == [
        Decimal("0.250"),
        Decimal("0.750"),
    ]


def test_under_21_gets_no_alcohol_allowance() -> None:  # 148.33(d)(2)
    r = run(Profile(**{**ADULT, "age": 20}), [bottle(ml=500, price=10)])
    assert r["allowance"].lines[0].status == "dutiable"


def test_beneficiary_direct_arrival_gives_2_litres() -> None:  # 148.33(d)(3)(ii)
    p = Profile(
        age=40,
        trip=Duration(value=6, unit="days"),
        direct_arrival_from="BB",
        exemption_used_last_30_days=False,
    )
    r = run(p, [bottle("rum", "spirits", n=2, ml=1000, abv=40, price=20, origin="BB")])
    assert r["allowance"].alcohol_allowance_l == Decimal(2) and r["bottom_line"] == [
        "nothing_to_pay"
    ]


def test_2_litres_need_1_litre_made_in_a_beneficiary_country() -> None:
    p = Profile(
        age=40,
        trip=Duration(value=6, unit="days"),
        direct_arrival_from="BB",
        exemption_used_last_30_days=False,
    )
    r = run(
        p,
        [
            bottle("rum", "spirits", ml=500, abv=40, price=20, origin="BB"),
            bottle("wine", n=2, ml=750, price=20, origin="FR"),
        ],
    )
    assert r["allowance"].alcohol_allowance_l == Decimal(1)


def test_2_litre_allowance_caps_other_origins_at_1_litre() -> None:
    p = Profile(
        age=40,
        trip=Duration(value=6, unit="days"),
        direct_arrival_from="JM",
        exemption_used_last_30_days=False,
    )
    r = run(
        p,
        [
            bottle("cognac", "spirits", n=2, ml=1000, abv=40, price=90, origin="FR"),
            bottle("rum", "spirits", n=1, ml=1000, abv=40, price=20, origin="JM"),
        ],
    )
    assert [a.exempt_l for a in r["allowance"].lines] == [
        Decimal("1.000"),
        Decimal("1.000"),
    ]


def test_tobacco_over_allowance_is_declared_not_taxed() -> (
    None
):  # CBP; rules.yaml tobacco_over_allowance
    r = run(Profile(**ADULT), [smokes(201, "cigarettes", price=0.3)])
    assert r["bottom_line"] == ["declare_detention_risk"] and r["total_usd"] == 0


def test_export_labelled_us_cigarettes_over_allowance_are_relinquished() -> (
    None
):  # 26 USC 5754, 5761
    r = run(Profile(**ADULT), [smokes(2, origin="US", export_labelled_us=True)])
    assert r["bottom_line"] == ["relinquish_excess"]


def test_under_21_tobacco_is_over_the_allowance() -> None:
    r = run(Profile(**{**ADULT, "age": 19}), [smokes(1, "pack", price=8)])
    assert r["bottom_line"] == ["declare_detention_risk"]


# ------------------------------------------------------------------ duty and excise


@pytest.mark.parametrize(
    ("origin", "rate", "basis"),
    [
        ("MX", Decimal(0), "free_program:S"),
        ("DO", Decimal(0), "free_program:P"),
        ("BY", Decimal("0.04"), "column2"),
        ("FR", Decimal("0.03"), "general"),
    ],
)
def test_flat_rate_by_origin(origin, rate, basis) -> None:  # HTSUS 9816.00.20
    assert duty_rate(origin) == (rate, basis)


def test_duty_and_excise_on_one_litre_of_spirits() -> None:
    # 2 x 1 L, 40%, $50, France: 1 L excess -> value $50, duty 3% = $1.50,
    # excise 1 / 3.785411784 gal x 0.8 x $13.50 = $2.853... -> $2.85
    r = run(
        Profile(**ADULT), [bottle("brandy", "spirits", n=2, ml=1000, abv=40, price=50)]
    )
    d = r["duty"].lines[0]
    assert (d.dutiable_value_usd, d.duty_usd, d.excise_usd, r["total_usd"]) == (
        Decimal(50),
        Decimal("1.50"),
        Decimal("2.85"),
        Decimal("4.35"),
    )


def test_beer_excise_is_per_barrel_over_31() -> None:
    r = run(
        Profile(**ADULT),
        [bottle("lager", "beer", n=6, ml=500, abv=5, price=2, origin="NL")],
    )
    # 2 L excess / 3.785411784 = 0.52834 gal x 18/31 = 0.30678 -> $0.31; value $8 x 3% = $0.24
    assert (r["duty"].excise_usd, r["duty"].duty_usd) == (
        Decimal("0.31"),
        Decimal("0.24"),
    )


def test_over_the_flat_rate_band_escalates() -> None:
    r = run(
        Profile(**ADULT),
        [bottle("whisky", "spirits", n=4, ml=700, abv=40, price=400, origin="GB")],
    )
    assert r["outcome"] == "escalated" and r["rule_id"] == "over_flat_rate_band"


def test_flat_rate_used_in_30_days_escalates() -> None:
    p = Profile(
        age=40, trip=Duration(value=5, unit="days"), exemption_used_last_30_days=True
    )
    assert run(p, [bottle(n=2)])["outcome"] == "escalated"


def test_rounding_is_half_up() -> None:
    assert (cents(dec("0.125")), dollars(dec("41.5"))) == (Decimal("0.13"), Decimal(42))


# ------------------------------------------------------------------ state flag and helpers


def test_state_flag_for_listed_state_only() -> None:
    assert lookup_state_rule(SArgs(arrival_state="tx")).name == "Texas"
    assert lookup_state_rule(SArgs(arrival_state="OH")) is None


def test_rule_match_reports_missing_facts() -> None:
    assert (
        match(
            {"category": ["alcohol"], "max_age": 20},
            {"category": "alcohol", "max_age": None},
        )
        == "unknown"
    )
    assert match({"over_allowance": True}, {"category": "alcohol"}) == "n/a"


def test_box_with_a_piece_count_as_size_is_a_box_of_n() -> None:
    # intake sometimes writes "a box of 10 cigars" as quantity {1, box}, size {10, cigars}
    line = BasketLine(
        item="cigars",
        category="tobacco",
        type="cigars",
        quantity=Amount(value=1, unit="box"),
        size=Amount(value=10, unit="cigars"),
    )
    assert normalise_units(NArgs(basket=[line]))[0].count == 10


def test_known_tobacco_units_ignore_a_size() -> None:
    line = BasketLine(
        item="cigarettes",
        category="tobacco",
        type="cigarettes",
        quantity=Amount(value=2, unit="cartons"),
        size=Amount(value=400, unit="pieces"),  # a total, not per carton
    )
    assert normalise_units(NArgs(basket=[line]))[0].count == 400
