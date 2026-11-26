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


@pytest.mark.parametrize(
    ("set_name", "label"), [("eval3", "eval-v3"), ("eval-gold2", "eval-v2 (gold-v2)")]
)
def test_v2_held_out_sets_refuse_without_a_matching_freeze(
    tmp_path, monkeypatch, capsys, set_name, label
):
    from eval import run_agent

    monkeypatch.setattr(freeze, "FROZEN", tmp_path / "none.json")
    monkeypatch.setattr(
        "sys.argv", ["run_agent.py", "--set", set_name, "--mode", "router"]
    )
    assert run_agent.main() == 1
    assert f"Refusing to run {label}" in capsys.readouterr().out


def test_every_set_file_exists():
    from eval import run_agent

    for name, path in run_agent.SETS.items():
        assert path.exists(), name
    assert set(run_agent.HELD_OUT) == {"eval", "eval3", "eval-gold2"}


@pytest.mark.skipif(not freeze.FROZEN.exists(), reason="no freeze recorded yet")
def test_code_matches_the_recorded_freeze():
    """After Day 9: a prompt or retrieval change must come with a new, logged freeze."""
    st = freeze.status()
    assert st["matches"], st["drift"]


def test_code_fingerprint_sees_a_code_change(tmp_path, monkeypatch):
    """agent v2: the freeze also hashes src/ and the rules and rates."""
    (tmp_path / "src" / "agent").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    f = tmp_path / "src" / "agent" / "x.py"
    f.write_text("A = 1\n")
    (tmp_path / "data" / "rules.yaml").write_text("a: 1\n")
    monkeypatch.setattr(freeze, "ROOT", tmp_path)
    before = freeze.code_fingerprint()
    f.write_text("A = 2\n")
    assert freeze.code_fingerprint()["sha256"] != before["sha256"]
    assert before["files"] == 2


def test_v1_freeze_kept():
    v1 = json.loads((freeze.ROOT / "eval" / "freeze_v1.json").read_text())
    assert v1["frozen_at"] == "2026-11-22" and "code" not in v1
