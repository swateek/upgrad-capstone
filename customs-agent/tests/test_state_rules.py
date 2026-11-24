"""Arrival-state flags: the SPEC's five by default, fifteen with STATE_RULES=all (stretch, Day 9)."""

from __future__ import annotations

import pytest

from src.tools.common import rules
from src.tools.lookup_state_rule import Args, covered_states, lookup_state_rule

SPEC = {"NY", "FL", "CA", "TX", "NJ"}
EXTENDED = {"GA", "IL", "MA", "WA", "PA", "VA", "MI", "AZ", "HI", "NV"}


def test_default_is_the_spec_five(monkeypatch):
    monkeypatch.delenv("STATE_RULES", raising=False)
    assert set(covered_states()) == SPEC
    assert (
        lookup_state_rule(Args(arrival_state="GA")) is None
    )  # eval gold: no flag for GA


def test_all_adds_the_ten(monkeypatch):
    monkeypatch.setenv("STATE_RULES", "all")
    assert set(covered_states()) == SPEC | EXTENDED
    f = lookup_state_rule(Args(arrival_state="hi"))
    assert (f.state, f.name) == ("HI", "Hawaii")
    assert f.source.startswith("https://") and f.general_note
    assert lookup_state_rule(Args(arrival_state="OH")) is None


def test_bad_mode_is_an_error(monkeypatch):
    monkeypatch.setenv("STATE_RULES", "everything")
    with pytest.raises(ValueError):
        covered_states()


def test_every_extended_state_has_a_checked_official_source():
    ext = rules()["flags"]["state_alcohol_limits"]["extended_states"]
    official = (
        ".gov",
        "malegislature.gov",
        "ilga.gov",
        "virginia.gov",
        "nv.us",
        "hawaii.gov",
    )
    for code, s in ext.items():
        assert {"name", "note", "source", "as_of"} <= set(s), code
        assert s["source"].startswith("https://"), code
        host = s["source"].split("/")[2]
        assert host.endswith(official), (code, host)
        assert len(s["note"]) < 300, code
    assert not set(ext) & SPEC


def test_eval_run_refuses_extended_states(monkeypatch, capsys):
    from eval import run_agent

    monkeypatch.setenv("STATE_RULES", "all")
    monkeypatch.setattr(
        "sys.argv", ["run_agent.py", "--set", "eval", "--mode", "router"]
    )
    assert run_agent.main() == 1
    assert "STATE_RULES=all" in capsys.readouterr().out


def test_no_test_leaves_the_mode_set():
    """Runs after the API tests in file order: the app's lifespan must not leak into the process."""
    import os

    assert os.environ.get("STATE_RULES") in (None, "spec")
