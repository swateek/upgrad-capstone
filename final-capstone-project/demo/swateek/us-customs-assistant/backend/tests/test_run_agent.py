"""The eval run harness, offline: a fake agent, temp output; resume and report."""

from eval import run_agent as ra


class FakeAgent:
    def __init__(self):
        self.calls = 0

    def ask(self, thread, text, mode=None, tags=None):
        self.calls += 1
        return {"outcome": "refused", "kind": "refused", "owe_usd": None, "citations": [],
                "bottom_line": "no", "meta": {"model_calls": 0, "tool_calls": 0, "tokens": 0,
                                              "seconds": 0.1, "events": []}}  # fmt: skip

    def state(self, thread):
        return {"facts": {"profile": {}, "basket": []}}


def test_run_resume_and_report(tmp_path, monkeypatch):
    monkeypatch.setattr(ra, "RUNS", tmp_path)
    rows = [r for r in ra.load("dev") if r["id"] in ("DV19", "DV20", "DV01")]
    agent = FakeAgent()
    ra.run("t", "dev", "planner", rows, agent, who=None)
    assert agent.calls == 3 and ra.done_ids("t") == {"DV01", "DV19", "DV20"}
    ra.run("t", "dev", "planner", rows, agent, who=None)  # resume: nothing left
    assert agent.calls == 3
    text = ra.report("t")
    assert "Turns correct: 2/3" in text and "| DV01 | 1 |" in text


def test_expected_calls_dev():
    rows = ra.load("dev")
    chat, emb, cap = ra.expected_calls(rows, "planner")
    assert (chat, emb, cap) == (72, 17, 230)
    assert ra.expected_calls(rows, "router")[0] == 72 - 17
