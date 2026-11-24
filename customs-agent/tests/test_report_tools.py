"""Day 12 report helpers: the token-distribution table and the figure label groups."""

import csv

from eval import report_figures, token_calls


def test_quantile_is_a_real_value_nearest_rank():
    v = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert token_calls.quantile(v, 0.5) == 50
    assert token_calls.quantile(v, 0.95) == 100
    assert token_calls.quantile([7], 0.95) == 7
    assert token_calls.quantile([], 0.5) == 0


def test_repair_calls_count_under_their_stage():
    assert token_calls.stage_of("intake_repair") == "intake"
    assert token_calls.stage_of("writer") == "writer"


def test_failure_groups_do_not_overlap():
    seen = set()
    for _, codes in report_figures.STAGES:
        assert not (codes & seen)
        seen |= codes


def test_final_label_uses_agreed_hand_label(tmp_path):
    p = tmp_path / "f.csv"
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["label", "human_label", "human_label_2"])
        w.writeheader()
        w.writerow(
            {
                "label": "RULES",
                "human_label": "GOLD_ERROR",
                "human_label_2": "GOLD_ERROR",
            }
        )
        w.writerow(
            {
                "label": "GUARD_MISS",
                "human_label": "GUARD_MISS",
                "human_label_2": "OTHER",
            }
        )
        w.writerow({"label": "EXTRACT_MISSED", "human_label": "", "human_label_2": ""})
    c = report_figures.final_labels(p)
    assert c == {"GOLD_ERROR": 1, "GUARD_MISS": 1, "EXTRACT_MISSED": 1}


def test_official_traces_are_rebuilt_and_tagged():
    """eval/push_traces.py: a recorded answer becomes a trace with the official tags, no model call."""
    from contextlib import contextmanager

    from eval import push_traces

    class Obs:
        def __init__(self, log, kw):
            self.log, self.trace_id = log, "t1"
            log.append(kw)

        def start_observation(self, **kw):
            return Obs(self.log, kw)

        def update(self, **kw):
            self.log.append({"update": kw})

        def end(self):
            pass

    log: list = []

    @contextmanager
    def root(**kw):
        yield Obs(log, kw)

    from src.tracing import LangfuseTracer

    tracer = LangfuseTracer.__new__(LangfuseTracer)
    tracer.client = type(
        "C", (), {"start_as_current_observation": staticmethod(root)}
    )()
    item = next(push_traces.items(False))
    assert push_traces.send(tracer, *item) == "t1"
    d, mode, set_, agent, rec, _q, score, _frozen = item
    tags = push_traces.tags_for(d, mode, set_, agent, score)
    assert tags[0] == "official-run" and "replayed" in tags
    assert {"correct", "wrong"} & set(tags)
    assert log[0]["metadata"]["question_id"] == rec["id"]
    assert log[0]["metadata"]["run"] == d
