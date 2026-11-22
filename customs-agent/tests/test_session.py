"""Conversations across turns (LangGraph + SQLite checkpointer), with a scripted model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.session import Sessions, TurnUpdate, apply_edit, first_affected, merge
from tests.test_agent import ScriptedLLM, fake_search

CONVS = {
    json.loads(x)["id"]: json.loads(x)
    for x in (Path(__file__).parents[1] / "eval" / "conversations.jsonl")
    .read_text()
    .splitlines()
}
OK_WRITER = {"advises_evasion": False}


def writer_for(
    total: str | None = None, text: str = "Declare it at the border."
) -> dict:
    bl = f"You owe ${total}." if total else "Nothing to pay."
    return {"bottom_line": bl, "explanation": text, "sources": [1]}


def sessions(tmp_path, llm) -> Sessions:
    return Sessions(llm, fake_search, db=tmp_path / "s.sqlite3", verify_with_llm=False)


def wine(n=2, size=None, price=45, origin="FR", abv=13.5, item="Bordeaux") -> dict:
    d = {
        "item": item,
        "category": "alcohol",
        "type": "wine",
        "quantity": {"value": n, "unit": "bottle"},
        "abv": abv,
        "unit_price_usd": price,
        "origin": origin,
    }
    if size:
        d["size"] = size
    return d


# ------------------------------------------------------------------ pure helpers


def test_merge_applies_only_what_changed() -> None:
    upd = TurnUpdate.model_validate(
        {
            "profile": {"age": 20},
            "item_updates": [{"line": 1, "quantity": {"value": 3, "unit": "bottle"}}],
        }
    )
    p, b, changed = merge({"age": 23}, [wine()], upd)
    assert (
        p["age"] == 20
        and b[0]["quantity"]["value"] == 3
        and set(changed) == {"age", "item1.quantity"}
    )


def test_first_affected_step() -> None:
    assert first_affected(["age"]) == "check_restrictions"
    assert first_affected(["trip"]) == "determine_exemption"
    assert first_affected(["trip", "item1.quantity"]) == "normalise_units"
    assert first_affected(["arrival_state"]) == "lookup_state_rule"


def test_apply_edit() -> None:
    p, _b, ch = apply_edit({"age": 29}, [wine()], {"field": "age", "value": 19})
    assert p["age"] == 19 and ch == ["age"]
    with pytest.raises(ValueError):
        apply_edit({}, [wine()], {"field": "shoe_size", "value": 9})


# ------------------------------------------------------------------ conversations


def test_clarify_then_terse_answers_are_tied_to_the_question(tmp_path) -> None:
    """C01-like: a bare 'no' answers the 30-day question it follows."""
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {},
                "basket": [
                    wine(
                        3, {"value": 750, "unit": "ml"}, 22, "ES", 13.5, "Spanish Rioja"
                    )
                ],
            }
        ],
        turn_intake=[
            {
                "request_kind": "assess",
                "profile": {"age": 38, "trip": {"value": 9, "unit": "days"}},
            },
            {
                "request_kind": "assess",
                "profile": {"exemption_used_last_30_days": False},
            },
        ],
        writer=[writer_for("1.46")],
    )
    s = sessions(tmp_path, llm)
    r1 = s.turn(
        "c",
        message="Bringing back 3 bottles of Spanish Rioja, 750 ml, 13.5%, $22 each. What do I owe?",
    )
    assert r1.answer.outcome == "clarify" and r1.answer.clarify_facts == [
        "age",
        "trip_length",
        "exemption_used_last_30_days",
    ]
    r2 = s.turn("c", message="I'm 38, 9 days in Spain")
    assert r2.answer.clarify_facts == ["exemption_used_last_30_days"]
    r3 = s.turn("c", message="no")
    assert (
        r3.answer.outcome == "answered"
        and r3.answer.total_usd == CONVS["C01"]["turns"][1]["gold"]["total_usd"]
    )


def test_correction_replans_only_dependent_steps(tmp_path) -> None:
    """C03: trip 3 days -> 30 hours: exemption, allowance and duty re-run; units and restrictions reused."""
    c = CONVS["C03"]
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {
                    "age": 35,
                    "trip": {"value": 3, "unit": "days"},
                    "exemption_used_last_30_days": False,
                },
                "basket": [wine(2, {"value": 750, "unit": "ml"}, 45, "FR")],
            }
        ],
        turn_intake=[
            {
                "request_kind": "assess",
                "profile": {"trip": {"value": 30, "unit": "hours"}},
            }
        ],
        writer=[writer_for("1.04"), writer_for("3.12")],
    )
    s = sessions(tmp_path, llm)
    r1 = s.turn("c", message=c["turns"][0]["user"])
    assert r1.answer.total_usd == c["turns"][0]["gold"]["total_usd"]
    r2 = s.turn("c", message=c["turns"][1]["user"])
    assert r2.answer.total_usd == c["turns"][1]["gold"]["total_usd"]
    replan = next(t for t in r2.trace if t.get("step") == "replan")
    assert replan["first_step"] == "determine_exemption"
    assert replan["reused"] == ["normalise_units", "check_restrictions"]


def test_edit_on_the_card_needs_no_reading(tmp_path) -> None:
    """C07: age edited to 19 on the card: no intake call, alcohol no longer duty-free."""
    c = CONVS["C07"]
    mezcal = {
        "item": "Mexican mezcal",
        "category": "alcohol",
        "type": "spirits",
        "quantity": {"value": 3, "unit": "bottle"},
        "size": {"value": 750, "unit": "ml"},
        "abv": 45,
        "unit_price_usd": 40,
        "origin": "MX",
    }
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {
                    "age": 29,
                    "trip": {"value": 5, "unit": "days"},
                    "direct_arrival_from": "MX",
                    "exemption_used_last_30_days": False,
                },
                "basket": [mezcal],
            }
        ],
        writer=[writer_for("4.01"), writer_for("7.22")],
    )
    s = sessions(tmp_path, llm)
    s.turn("c", message=c["turns"][0]["user"])
    r2 = s.turn("c", edit={"field": "age", "value": 19})
    assert r2.answer.total_usd == c["turns"][1]["gold"]["total_usd"]
    assert "intake" not in [x["stage"] for x in r2.usage.steps]


def test_two_unanswered_rounds_use_the_default_and_escalate(tmp_path) -> None:
    """C08: 30-day use never answered: default 'used' -> flat rate treated as used -> escalate."""
    rum = {
        "item": "Colombian rum",
        "category": "alcohol",
        "type": "spirits",
        "quantity": {"value": 2, "unit": "bottle"},
        "size": {"value": 1, "unit": "litre"},
        "abv": 40,
        "unit_price_usd": 25,
        "origin": "CO",
    }
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {"age": 40, "trip": {"value": 1, "unit": "weeks"}},
                "basket": [rum],
            }
        ],
        turn_intake=[{"request_kind": "assess", "profile": {}}],
    )
    s = sessions(tmp_path, llm)
    turns = CONVS["C08"]["turns"]
    outs = [s.turn("c", message=t["user"]) for t in turns]
    assert [o.answer.outcome for o in outs] == [t["gold"]["outcome"] for t in turns]
    assert outs[2].assumptions == ["exemption_used_last_30_days"]


def test_two_unanswered_rounds_abv_default_answers(tmp_path) -> None:
    """C09: ABV never given: spirits 40% -> answered, listed under assumptions."""
    w = {
        "item": "Irish whiskey",
        "category": "alcohol",
        "type": "spirits",
        "quantity": {"value": 2, "unit": "bottle"},
        "size": {"value": 1, "unit": "litre"},
        "unit_price_usd": 40,
        "origin": "IE",
    }
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {
                    "age": 50,
                    "trip": {"value": 10, "unit": "days"},
                    "exemption_used_last_30_days": False,
                },
                "basket": [w],
            }
        ],
        turn_intake=[{"request_kind": "assess", "profile": {}}],
        writer=[writer_for("4.05", "Spirits taken as 40%. Declare them.")],
    )
    s = sessions(tmp_path, llm)
    turns = CONVS["C09"]["turns"]
    outs = [s.turn("c", message=t["user"]) for t in turns]
    assert [o.answer.outcome for o in outs] == ["clarify", "clarify", "answered"]
    assert outs[2].answer.total_usd == turns[2]["gold"]["total_usd"] and outs[
        2
    ].assumptions == ["abv"]
    assert any("40%" in a for a in outs[2].card["assumptions"])


def test_one_round_asks_size_with_the_trip_facts(tmp_path) -> None:
    """C13: size, trip and 30-day use in one message (SPEC 5.2 as amended)."""
    jw = {
        "item": "Johnnie Walker Blue",
        "category": "alcohol",
        "type": "spirits",
        "quantity": {"value": 1, "unit": "bottle"},
    }
    llm = ScriptedLLM(
        intake=[{"request_kind": "assess", "profile": {"age": 21}, "basket": [jw]}],
        turn_intake=[
            {
                "request_kind": "assess",
                "profile": {
                    "trip": {"value": 8, "unit": "days"},
                    "exemption_used_last_30_days": False,
                },
                "item_updates": [
                    {
                        "line": 1,
                        "size": {"value": 1, "unit": "litre"},
                        "unit_price_usd": 250,
                    }
                ],
            }
        ],
        writer=[writer_for(None, "One litre fits your allowance.")],
    )
    s = sessions(tmp_path, llm)
    t = CONVS["C13"]["turns"]
    r1 = s.turn("c", message=t[0]["user"])
    assert r1.answer.clarify_facts == t[0]["gold"]["clarify_facts"]
    r2 = s.turn("c", message=t[1]["user"])
    assert r2.answer.outcome == "answered" and [
        b.type for b in r2.answer.bottom_line
    ] == ["nothing_to_pay"]


def test_refusal_mid_conversation_keeps_the_facts(tmp_path) -> None:
    """C11: evasion is refused; the conversation's facts survive for the next question."""
    port = wine(3, {"value": 750, "unit": "ml"}, 30, "PT", 20, "Portuguese port")
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {
                    "age": 45,
                    "trip": {"value": 6, "unit": "days"},
                    "exemption_used_last_30_days": False,
                },
                "basket": [port],
            }
        ],
        writer=[writer_for("2.02")],
    )
    s = sessions(tmp_path, llm)
    s.turn("c", message=CONVS["C11"]["turns"][0]["user"])
    r2 = s.turn("c", message="Can I hide two of the bottles so I don't pay?")
    assert r2.answer.outcome == "refused"
    st = s.state("c")
    assert st["basket"][0]["item"] == "Portuguese port" and len(st["history"]) == 1


def test_sessions_are_separate_and_survive_a_restart(tmp_path) -> None:
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {},
                "basket": [wine(2, {"value": 750, "unit": "ml"})],
            }
        ]
    )
    s = sessions(tmp_path, llm)
    s.turn("a", message="2 bottles of Bordeaux, 750 ml, 13.5%, $45 each")
    assert s.state("b")["basket"] is None
    again = sessions(tmp_path, llm)  # new process, same database
    assert again.state("a")["basket"][0]["item"] == "Bordeaux"


def test_run_conversations_scores_turns_and_conversations(tmp_path) -> None:
    from eval.run_conversations import run

    rum = {
        "item": "Colombian rum",
        "category": "alcohol",
        "type": "spirits",
        "quantity": {"value": 2, "unit": "bottle"},
        "size": {"value": 1, "unit": "litre"},
        "abv": 40,
        "unit_price_usd": 25,
        "origin": "CO",
    }
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {"age": 40, "trip": {"value": 1, "unit": "weeks"}},
                "basket": [rum],
            }
        ],
        turn_intake=[{"request_kind": "assess", "profile": {}}],
    )
    s = run(sessions(tmp_path, llm), "router", "t", only=["C08"], results=tmp_path)
    assert s["turns"] == 3 and s["conversation_accuracy"] == 1.0


def test_a_failing_turn_is_recorded_not_raised(tmp_path) -> None:
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {},
                "basket": [wine(2, {"value": 750, "unit": "ml"})],
            }
        ]
    )
    s = sessions(tmp_path, llm)
    s.turn("c", message="2 bottles of Bordeaux, 750 ml, 13.5%, $45 each")
    r = s.turn("c", message="I'm 35")  # no turn_intake scripted: the model call fails
    assert r.answer.outcome == "escalated" and r.error
    assert s.state("c")["basket"][0]["item"] == "Bordeaux"  # earlier facts survive


# ------------------------------------------------------------------ fixes from day7-conv


def test_guessed_abv_is_dropped_and_asked(tmp_path) -> None:
    """C09: the model wrote 40% although the question gives no ABV."""
    w = {
        "item": "Irish whiskey",
        "category": "alcohol",
        "type": "spirits",
        "quantity": {"value": 2, "unit": "bottle"},
        "size": {"value": 1, "unit": "litre"},
        "abv": 40,
        "unit_price_usd": 40,
        "origin": "IE",
    }
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {
                    "age": 50,
                    "trip": {"value": 10, "unit": "days"},
                    "exemption_used_last_30_days": False,
                },
                "basket": [w],
            }
        ]
    )
    r = sessions(tmp_path, llm).turn("c", message=CONVS["C09"]["turns"][0]["user"])
    assert r.answer.outcome == "clarify" and r.answer.clarify_facts == ["abv"]


def test_guessed_origin_of_a_risky_item_is_dropped(tmp_path) -> None:
    """C10: vodka with a made-up origin (Italy): the origin question must still be asked."""
    v = {
        "item": "vodka",
        "category": "alcohol",
        "type": "spirits",
        "quantity": {"value": 2, "unit": "bottle"},
        "size": {"value": 750, "unit": "ml"},
        "abv": 40,
        "unit_price_usd": 25,
        "origin": "IT",
    }
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {"age": 31, "direct_arrival_from": "IT"},
                "basket": [v],
            }
        ],
        turn_intake=[
            {
                "request_kind": "assess",
                "profile": {"trip": {"value": 7, "unit": "days"}},
                "item_updates": [{"line": 1, "origin": "PL"}],
            }
        ],
        writer=[
            {
                "bottom_line": "You owe $1.94.",
                "explanation": "Declare it.",
                "sources": [1],
            }
        ],
    )
    s = sessions(tmp_path, llm)
    t = CONVS["C10"]["turns"]
    r1 = s.turn("c", message=t[0]["user"])
    assert r1.answer.clarify_facts == t[0]["gold"]["clarify_facts"]
    r2 = s.turn(
        "c", message=t[1]["user"]
    )  # "first trip this year": not used, set in code
    assert (
        r2.answer.outcome == "answered"
        and r2.answer.total_usd == t[1]["gold"]["total_usd"]
    )


def test_under_21_working_states_a_zero_allowance() -> None:
    from src.agent import card
    from src.agent.router import route
    from tests._chain import line_from_fact, profile_from_fact
    from tests.test_agent import DEV

    d = DEV["D09"]
    r = route(
        profile_from_fact(d["facts"]["profile"]),
        [line_from_fact(f) for f in d["facts"]["basket"]],
    )
    assert any("alcohol allowance 0 L: under 21" in w for w in card.working(r))


def test_turn_intake_prompt_does_not_treat_declining_as_evasion() -> None:
    from src.agent.session import TURN_INTAKE

    assert '"Does that matter?"' in TURN_INTAKE and "I'd rather not say" in TURN_INTAKE


def test_bare_number_answers_the_abv_question(tmp_path) -> None:
    """Owner's test (Day 9, Honolulu sake): "35" in reply to "What is the ABV?" was dropped by
    grounding (no % sign), asked again, then defaulted to 40% and escalated."""
    sake = {
        "item": "sake",
        "category": "alcohol",
        "type": "spirits",
        "quantity": {"value": 3, "unit": "bottle"},
        "size": {"value": 750, "unit": "ml"},
        "abv": 15,  # invented by the model: grounding drops it
        "unit_price_usd": 10,
        "origin": "JP",
        "bought_where": "JP",
    }
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {
                    "trip": {"value": 10, "unit": "days"},
                    "direct_arrival_from": "JP",
                    "arrival_state": "HI",
                },
                "basket": [sake],
            }
        ],
        turn_intake=[
            {
                "request_kind": "assess",
                "profile": {"age": 21, "exemption_used_last_30_days": False},
            },
            {
                "request_kind": "assess",
                "profile": {},
                "item_updates": [{"line": 1, "abv": 35}],
            },
        ],
        writer=[
            {
                "bottom_line": "You owe $3.63 on the sake.",
                "explanation": "Your alcohol allowance is 1 L. You brought 2.25 L, so 1.25 L is over. "
                "Duty is 3% of $17.00 ($0.51) and federal excise tax is $3.12. Total is $3.63.",
                "sources": [1],
            }
        ],
    )
    s = sessions(tmp_path, llm)
    q = "Flying into Honolulu after 10 days in Japan, 3 bottles of sake, 10$ each of 750ml, what do i owe"
    r1 = s.turn("c", message=q)
    assert r1.answer.outcome == "clarify" and "abv" not in s.state("c")["basket"][0]
    r2 = s.turn("c", message="i'm of age and no")
    assert r2.answer.clarify_facts == ["abv"]
    r3 = s.turn("c", message="35")
    assert r3.answer.outcome == "answered", r3.reason
    assert s.state("c")["basket"][0]["abv"] == 35
    assert r3.answer.total_usd == 3.63 and r3.assumptions == []


def test_a_number_not_in_the_reply_is_still_dropped(tmp_path) -> None:
    """The ABV answer rule only keeps a number the traveller wrote: a guess stays a guess."""
    from src.agent.session import Sessions  # noqa: F401  (same module as above)

    sake = {
        "item": "sake",
        "category": "alcohol",
        "type": "spirits",
        "quantity": {"value": 3, "unit": "bottle"},
        "size": {"value": 750, "unit": "ml"},
        "unit_price_usd": 10,
        "origin": "JP",
    }
    llm = ScriptedLLM(
        intake=[
            {
                "request_kind": "assess",
                "profile": {
                    "age": 30,
                    "trip": {"value": 10, "unit": "days"},
                    "exemption_used_last_30_days": False,
                },
                "basket": [sake],
            }
        ],
        turn_intake=[
            {
                "request_kind": "assess",
                "profile": {},
                "item_updates": [{"line": 1, "abv": 15}],
            }
        ],
        writer=[writer_for("1.00")],
    )
    s = sessions(tmp_path, llm)
    s.turn(
        "c",
        message="3 bottles of sake, 750 ml, $10 each, 10 days in Japan, I'm 30, first trip this year",
    )
    r = s.turn("c", message="not sure, it's the usual kind")
    assert r.answer.outcome == "clarify" and r.answer.clarify_facts == ["abv"]
