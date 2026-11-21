"""Tobacco over the allowance is never taxed (R5): a working sentence that puts duty or excise on
tobacco is dropped, and the seizure wording on the card stays. Offline; no model call."""

from customs.agent.graph import drop_unsourced
from customs.agent.verifier import tobacco_taxed_sentences
from customs.agent.writer import WriterOut


def test_flags_duty_and_excise_on_tobacco():
    line = "Cigarettes over the allowance may be subject to duty and excise [S3]."
    assert tobacco_taxed_sentences([line]) == [line]


def test_allows_not_taxed_duty_free_and_wine_excise():
    ok = [
        "Tobacco over the allowance is not taxed; it may be detained or seized [S3].",
        "The 200 cigarettes within the allowance are duty-free [S2].",
        "Federal excise on the wine is $0.57 [S4].",
    ]
    assert tobacco_taxed_sentences(ok) == []


def test_drop_removes_the_taxed_sentence_and_keeps_the_rest():
    out = WriterOut(
        bottom_line="The cigarettes may be at risk of seizure.",
        working=[
            "Your trip qualifies for the $800 exemption [S1].",
            "Cigarettes over the allowance may be subject to duty and excise [S3].",
        ],
    )
    problems = ["tobacco is never taxed here, so this sentence is dropped: 'Cigarettes ...'"]
    new, left = drop_unsourced(out, problems)
    assert left == []
    assert new.working == ["Your trip qualifies for the $800 exemption [S1]."]
    assert new.bottom_line == out.bottom_line


def test_other_problems_still_escalate():
    out = WriterOut(bottom_line="x", working=["Cigarettes may be taxed [S1]."])
    other = ["typed number '3': use a figure handle"]
    new, left = drop_unsourced(out, other)
    assert left == other
    assert new is out
