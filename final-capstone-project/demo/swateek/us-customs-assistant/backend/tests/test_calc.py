"""Calculators (SPEC §5): one test group per signed-off rule, the corrected business-case examples,
and the clarify trigger. The dev-set gold comparison is in test_calc_dev.py."""

from decimal import Decimal

import pytest

from customs.tools.calc import assess, excise_per_litre, new_case, step_normalise
from customs.tools.facts import missing_facts
from customs.tools.models import Line, Profile


def P(**kw) -> Profile:
    base = {"age": 40, "trip_hours": 240, "exemption_used_last_30_days": False}
    return Profile(**{**base, **kw})


def wine(n=1, ml=750, usd=None, origin="IT", **kw) -> Line:
    return Line(
        item="wine", quantity=n, unit="bottle", container_ml=ml, value_usd=usd, origin=origin, **kw
    )


def spirits(n=1, ml=750, usd=None, origin="GB", abv=40, **kw) -> Line:
    return Line(
        item="spirits",
        quantity=n,
        unit="bottle",
        container_ml=ml,
        abv=abv,
        value_usd=usd,
        origin=origin,
        **kw,
    )


def fig(a, name) -> str | None:
    return a.figure(name)


# --- business-case examples, corrected (docs/regulatory-checks.md) --------------------------------


def test_example_1_wine_from_italy_is_2_97():
    a = assess(P(age=34, arrived_directly_from="IT"), [wine(4, usd=120)])
    assert (a.outcome, a.kind, a.owe_usd) == ("answered", "owe", Decimal("2.97"))
    assert fig(a, "duty_usd_1") == "2.40" and fig(a, "excise_usd_1") == "0.57"
    assert fig(a, "dutiable_ml_1") == "2000" and fig(a, "dutiable_value_usd_1") == "80.00"


def test_example_2_cuban_goods_from_cancun_are_prohibited():
    basket = [
        Line(item="cigars", quantity=25, unit="each", origin="CU", bought_in="MX"),
        Line(item="spirits", quantity=1, unit="bottle", origin="CU", bought_in="MX"),
    ]
    a = assess(Profile(arrived_directly_from="MX"), basket)
    assert (a.outcome, a.kind, a.owe_usd) == ("answered", "prohibited", Decimal("0.00"))
    assert "R4:third_country" in a.rule_refs and "cuban_prohibited" in a.notes
    assert a.figures == []  # nothing assessable remains


def test_example_3_two_cartons_one_over_at_seizure_risk():
    a = assess(P(arrived_directly_from="AE"), [Line(item="cigarettes", quantity=2, unit="carton")])
    assert a.kind == "seizure_risk" and fig(a, "excess_sticks_1") == "200"
    assert "seizure_risk" in a.notes and "R5" in a.rule_refs


def test_example_4_tijuana_day_trip_gets_800_and_owes_nothing():
    a = assess(P(trip_hours="<48", arrived_directly_from="MX"), [spirits(origin="MX", usd=35)])
    assert (a.exemption_usd, a.kind, a.owe_usd) == (800, "nothing_owed", Decimal("0.00"))


def test_example_4_repeat_trip_within_30_days_is_all_or_nothing():
    p = P(
        trip_hours="<48",
        arrived_directly_from="MX",
        exemption_used_last_30_days=True,
        arrival_state="CA",
    )
    a = assess(p, [spirits(origin="MX", usd=35)])
    assert a.exemption_usd == 200 and fig(a, "dutiable_ml_1") == "750"
    assert fig(a, "duty_usd_1") == "0.00" and fig(a, "excise_usd_1") == "2.14"  # USMCA duty free
    assert {"fta_caveat", "state_flag:CA"} <= set(a.notes)
    assert {"R9", "R1", "R7", "R8", "state:CA"} <= set(a.rule_refs)


# --- R1 $200 all-or-nothing -------------------------------------------------------------------------


def test_r1_within_all_limits_everything_exempt():
    basket = [
        Line(item="cigarettes", quantity=1, unit="pack", value_usd=12),
        spirits(ml=100, usd=8, origin=None),
    ]
    a = assess(P(trip_hours=10, arrived_directly_from="CA"), basket)
    assert (a.exemption_usd, a.kind) == (200, "nothing_owed")


def test_r1_one_line_over_breaks_everything_including_tobacco():
    basket = [
        Line(item="cigarettes", quantity=2, unit="pack", value_usd=24),
        wine(ml=375, usd=15, origin="CA"),
    ]
    a = assess(P(trip_hours="<48", arrived_directly_from="CA"), basket)
    assert a.kind == "mixed" and fig(a, "excess_sticks_1") == "40"  # Decision A1
    assert fig(a, "dutiable_ml_2") == "375" and a.owe_usd == Decimal("0.11")


def test_r1_value_over_200_breaks_it():
    a = assess(
        P(trip_hours=20, arrived_directly_from="CA"), [spirits(ml=100, usd=250, origin="FR")]
    )
    assert fig(a, "dutiable_ml_1") == "100"


# --- R2 Caribbean Basin 2 litres (Decision A: CBP's list) --------------------------------------


def test_r2_two_litres_when_one_litre_is_a_beneficiary_product():
    a = assess(P(arrived_directly_from="JM"), [spirits(2, ml=1000, usd=50, origin="JM")])
    assert fig(a, "alcohol_allowance_ml") == "2000" and a.kind == "nothing_owed"
    assert "R2" in a.rule_refs


def test_r2_cbp_list_includes_dominican_republic():
    a = assess(P(arrived_directly_from="DO"), [spirits(2, usd=56, origin="DO")])
    assert fig(a, "alcohol_allowance_ml") == "2000"


def test_r2_no_beneficiary_product_means_one_litre():
    basket = [spirits(usd=50, origin="GB"), spirits(usd=30, origin="SE")]
    a = assess(P(arrived_directly_from="BS"), basket)
    assert fig(a, "alcohol_allowance_ml") == "1000"


# --- R3 under 21 (Decision B for tobacco) ------------------------------------------------------


def test_r3_under_21_no_alcohol_and_no_tobacco_allowance():
    basket = [
        wine(ml=1000, usd=25, origin="FR", abv=12),
        Line(item="cigarettes", quantity=1, unit="carton"),
    ]
    a = assess(P(age=20, arrived_directly_from="FR"), basket)
    assert fig(a, "alcohol_allowance_ml") == "0" and fig(a, "dutiable_ml_1") == "1000"
    assert fig(a, "excess_sticks_2") == "200" and a.kind == "mixed"
    assert "R3" in a.rule_refs


# --- R4 Cuban origin ------------------------------------------------------------------------------


def test_r4_bought_in_cuba_uses_the_cuba_citations():
    a = assess(
        Profile(arrived_directly_from="CU"),
        [Line(item="cigars", quantity=10, origin="CU", bought_in="CU")],
    )
    assert "R4:acquired_in_cuba" in a.rule_refs


def test_r4_cuban_line_removed_rest_assessed():
    basket = [spirits(ml=700, usd=30, origin="CU", bought_in="ES"), wine(2, usd=30, origin="ES")]
    a = assess(P(arrived_directly_from="ES"), basket)
    assert a.kind == "mixed" and fig(a, "dutiable_ml_2") == "500"
    assert "exempt_ml_1" not in {f.name for f in a.figures}


# --- R5 / R6 tobacco ------------------------------------------------------------------------------


def test_r5_tobacco_never_taxed():
    a = assess(P(arrived_directly_from="DO"), [Line(item="cigars", quantity=150, origin="DO")])
    assert fig(a, "excess_sticks_1") == "50" and a.owe_usd == Decimal("0.00")


def test_r6_us_export_labelled_relinquish_note():
    line = Line(
        item="cigarettes", quantity=3, unit="carton", origin="US", us_made_export_labelled=True
    )
    a = assess(P(arrived_directly_from="DE"), [line])
    assert fig(a, "excess_sticks_1") == "400"
    assert {"seizure_risk", "us_export_labelled_relinquish"} <= set(a.notes) and "R6" in a.rule_refs


# --- R7 duty: 3%, Column 2 4%, partner free, $1,000 cap ---------------------------------------------


def test_r7_column2_is_four_percent():
    a = assess(
        P(trip_hours=">=48", arrived_directly_from="LT"), [spirits(2, ml=700, usd=40, origin="BY")]
    )
    assert fig(a, "duty_rate_1") == "0.04" and fig(a, "duty_usd_1") == "0.46"
    assert a.owe_usd == Decimal("1.60")


def test_r7_partner_product_is_duty_free_with_caveat():
    a = assess(P(arrived_directly_from="CL"), [wine(4, usd=60, origin="CL", abv=13.5)])
    assert fig(a, "duty_rate_1") == "0" and "fta_caveat" in a.notes


def test_r7_cap_is_reached_only_through_the_800_basket_cap():
    # Dutiable value never exceeds the in-scope basket value, and a basket over $800 already
    # escalates (R11), so in v1 the $1,000 flat-rate cap (R7) is never the first cap hit.
    a = assess(P(arrived_directly_from="FR"), [spirits(3, ml=1000, usd=1500, origin="FR")])
    assert a.outcome == "escalated" and a.escalation_reason == "basket_over_800"


def test_r7_value_unknown_shows_excise_and_note():
    a = assess(P(trip_hours=120, arrived_directly_from="DE"), [wine(3, origin="DE")])
    assert fig(a, "duty_usd_1") is None and fig(a, "excise_usd_1") == "0.35"
    assert "value_unknown_duty_note" in a.notes and a.owe_usd == Decimal("0.35")


# --- R8 excise classes ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("item", "abv", "per_litre"),
    [
        ("spirits", 40, "2.853"),  # 13.50 x 0.8 / 3.785
        ("wine", 13, "0.2827"),  # 1.07 / 3.785
        ("wine", 20, "0.4148"),  # 1.57
        ("wine", 23, "0.8321"),  # 3.15
        ("wine", 30, "2.140"),  # over 24% taxed as spirits (60 proof)
        ("sparkling_wine", 12, "0.8982"),  # 3.40
        ("beer", 5, "0.1534"),  # 18 / 31 / 3.785
        ("liqueur", 25, "1.783"),  # a distilled spirit
    ],
)
def test_r8_excise_per_litre(item, abv, per_litre):
    case = new_case(P(), [Line(item=item, quantity=1, unit="l", abv=abv)])
    step_normalise(case)
    got = excise_per_litre(case.lines[0], case.t)
    assert abs(got - Decimal(per_litre)) < Decimal("0.0005")


def test_r8_beer_and_sparkling_in_a_basket():
    beer = Line(
        item="beer", quantity=12, unit="can", container_ml=500, abv=5, value_usd=24, origin="DE"
    )
    a = assess(P(arrived_directly_from="DE"), [beer])
    assert fig(a, "duty_usd_1") == "0.60" and fig(a, "excise_usd_1") == "0.77"


# --- R9 which exemption -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hours", "frm", "used", "expected"),
    [
        (240, "IT", False, 800),
        (47, "IT", False, 200),
        (48, "IT", False, 800),
        ("<48", "MX", False, 800),  # Mexico: no minimum stay
        ("<48", "CA", False, 200),  # Canada is not excepted
        (240, "IT", True, 200),  # used in the last 30 days
        ("<48", "MX", True, 200),
    ],
)
def test_r9_exemption(hours, frm, used, expected):
    a = assess(
        P(trip_hours=hours, arrived_directly_from=frm, exemption_used_last_30_days=used),
        [wine(usd=20, origin=frm)],
    )
    assert a.exemption_usd == expected


# --- R10 large quantity, R11 allocation, R11 basket cap ------------------------------------------


def test_r10_over_12_litres_escalates_with_note():
    basket = [wine(16, usd=192, origin="ES"), spirits(ml=1000, usd=30, origin="ES")]
    a = assess(P(arrived_directly_from="ES"), basket)
    assert a.outcome == "escalated" and a.rule_refs == ["R10"]
    assert "large_quantity" in a.notes and not any(
        f.unit == "usd" and f.name != "exemption_usd" for f in a.figures
    )


def test_r10_exactly_12_litres_is_not_flagged():
    a = assess(P(arrived_directly_from="ES"), [wine(16, usd=100, origin="ES")])
    assert a.outcome == "answered"


def test_r11_highest_cost_per_litre_fills_the_allowance_first():
    basket = [wine(2, usd=40, origin="ES"), spirits(ml=1000, usd=35, origin="ES")]
    a = assess(P(arrived_directly_from="ES"), basket)
    assert fig(a, "exempt_ml_2") == "1000" and fig(a, "dutiable_ml_1") == "1500"
    assert a.owe_usd == Decimal("1.62") and "R11" in a.rule_refs


def test_r11_not_cited_for_a_single_line():
    a = assess(P(arrived_directly_from="FR"), [spirits(2, usd=180, origin="FR")])
    assert "R11" not in a.rule_refs and a.owe_usd == Decimal("3.23")


def test_r11_basket_over_800_escalates():
    a = assess(P(arrived_directly_from="FR"), [spirits(1, ml=750, usd=900, origin="FR")])
    assert a.escalation_reason == "basket_over_800"


# --- R12 ambiguous brands (Decision E), scope, states ---------------------------------------------


def test_r12_ambiguous_brand_unknown_origin_is_possibly_cuban():
    line = Line(item="cigars", quantity=6, origin="unknown", brand="Cohiba", bought_in="DO")
    a = assess(P(arrived_directly_from="DO"), [line])
    assert a.kind == "prohibited" and {"R12", "R4:third_country"} <= set(a.rule_refs)
    assert "possibly_cuban_declare" in a.notes


def test_r12_ambiguous_brand_with_stated_origin_is_normal():
    line = Line(item="cigars", quantity=6, origin="DO", brand="Montecristo")
    a = assess(P(arrived_directly_from="DO"), [line])
    assert a.kind == "nothing_owed" and "R12" not in a.rule_refs


@pytest.mark.parametrize(
    ("profile", "note"),
    [
        (Profile(us_resident=False), "scope_note:non_resident"),
        (Profile(arrived_directly_from="VI"), "scope_note:insular"),
        (Profile(crew=True), "scope_note:crew"),
        (Profile(shipped=True), "scope_note:shipped"),
    ],
)
def test_scope_profiles(profile, note):
    a = assess(profile, [wine(usd=20)])
    assert a.outcome == "out_of_scope" and note in a.notes


def test_other_goods_only_is_out_of_scope():
    a = assess(P(), [Line(item="other", quantity=5, other_kind="vapes_nicotine")])
    assert a.outcome == "out_of_scope" and a.notes == ["scope_note:vapes_nicotine"]


def test_russian_alcohol_scope_note():
    a = assess(
        P(arrived_directly_from="FI"), [spirits(origin="RU", usd=20), wine(usd=20, origin="FR")]
    )
    assert "scope_note:russian" in a.notes and fig(a, "exempt_ml_2") == "750"


def test_state_flag_and_generic_note():
    a = assess(P(arrived_directly_from="IT", arrival_state="NY"), [wine(3, usd=60, abv=13)])
    assert "state_flag:NY" in a.notes and "state:NY" in a.rule_refs
    b = assess(P(arrived_directly_from="IT"), [wine(3, usd=60, abv=13)])
    assert "generic_state_note" in b.notes


def test_defaults_are_recorded_for_facts_relied_on():
    a = assess(
        P(arrived_directly_from="GB"),
        [Line(item="spirits", quantity=2, unit="bottle", value_usd=80, origin="GB")],
    )
    assert any("750 ml" in d for d in a.defaults_used) and any(
        "40% ABV" in d for d in a.defaults_used
    )


# --- clarify trigger (SPEC §6) ------------------------------------------------------------------------


def test_clarify_business_case_example_1_asks_age_30_days_and_state():
    p = Profile(trip_hours=240, arrived_directly_from="IT")
    assert missing_facts(p, [wine(4, usd=120)]) == [
        "age_21_plus",
        "exemption_used_last_30_days",
        "arrival_state",
    ]


def test_clarify_nothing_missing_and_state_never_asked_alone():
    p = P(trip_hours="<48", arrived_directly_from="MX")
    assert missing_facts(p, [spirits(origin="MX", usd=35)]) == []


def test_clarify_value_only_for_dutiable_lines():
    p = P(trip_hours=120, arrived_directly_from="DE", arrival_state="NY")
    assert missing_facts(p, [wine(1, origin="DE")]) == []  # inside the allowance
    assert missing_facts(p, [wine(3, origin="DE")]) == ["value_usd_of_line"]


def test_clarify_origin_for_partner_country_dutiable_line():
    p = P(arrived_directly_from="PE", arrival_state="FL")
    line = Line(
        item="spirits",
        quantity=3,
        unit="bottle",
        container_ml=750,
        abv=40,
        value_usd=75,
        bought_in="PE",
    )
    assert missing_facts(p, [line]) == ["origin_country_of_line"]


def test_clarify_origin_for_2_litre_claim():
    p = P(arrived_directly_from="JM", arrival_state="FL")
    line = Line(
        item="spirits",
        quantity=2,
        unit="bottle",
        container_ml=1000,
        abv=40,
        value_usd=50,
        bought_in="JM",
    )
    assert "origin_country_of_line" in missing_facts(p, [line])


def test_clarify_ambiguous_brand_and_no_clarify_for_all_cuban():
    p = P(arrived_directly_from="DO")
    assert missing_facts(p, [Line(item="cigars", quantity=6, brand="Cohiba")]) == [
        "origin_country_of_line"
    ]
    cuban = [Line(item="cigars", quantity=25, origin="CU")]
    assert missing_facts(Profile(arrived_directly_from="MX"), cuban) == []


def test_clarify_tobacco_only_does_not_ask_state():
    p = Profile(trip_hours=">=48", arrived_directly_from="AE")
    assert missing_facts(p, [Line(item="cigarettes", quantity=2, unit="carton")]) == [
        "age_21_plus",
        "exemption_used_last_30_days",
    ]
