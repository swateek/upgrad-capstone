"""Day 9 freeze (eval/freeze.py): drift is detected, and the official run refuses to start."""

from __future__ import annotations

import json

import pytest

from eval import freeze


def test_current_has_every_prompt_and_setting():
    now = freeze.current()
    assert set(now["prompts"]) == {
        "intake",
        "writer",
        "verify_evasion",
        "planner",
        "turn_intake",
    }
    assert now["retrieval"]["rrf_k"] == 60 and now["retrieval"]["max_k"] == 5
    assert now["budget"] == {
        "max_tool_steps": 10,
        "max_tokens_per_question": 12_000,
        "max_plan_steps": 10,
    }


def test_drift_is_reported(tmp_path, monkeypatch):
    path = tmp_path / "freeze.json"
    monkeypatch.setattr(freeze, "FROZEN", path)
    assert freeze.status() == {"frozen": False}
    path.write_text(json.dumps(freeze.current()))
    assert freeze.status()["matches"]
    from src.agent import prompts

    monkeypatch.setattr(prompts, "WRITER", prompts.WRITER + " Be brief.")
    st = freeze.status()
    assert not st["matches"] and st["drift"][0].startswith("prompts.writer")


def test_reranker_env_counts(tmp_path, monkeypatch):
    path = tmp_path / "freeze.json"
    monkeypatch.setattr(freeze, "FROZEN", path)
    path.write_text(json.dumps(freeze.current()))
    monkeypatch.setenv("RERANKER", "none")
    assert any(d.startswith("retrieval.reranker") for d in freeze.status()["drift"])


def test_eval_run_refuses_without_a_matching_freeze(tmp_path, monkeypatch, capsys):
    from eval import run_agent

    monkeypatch.setattr(freeze, "FROZEN", tmp_path / "none.json")
    monkeypatch.setattr(
        "sys.argv", ["run_agent.py", "--set", "eval", "--mode", "router"]
    )
    assert run_agent.main() == 1
    assert "Refusing to run eval-v2" in capsys.readouterr().out


@pytest.mark.skipif(not freeze.FROZEN.exists(), reason="no freeze recorded yet")
def test_code_matches_the_recorded_freeze():
    """After Day 9: a prompt or retrieval change must come with a new, logged freeze."""
    st = freeze.status()
    assert st["matches"], st["drift"]
