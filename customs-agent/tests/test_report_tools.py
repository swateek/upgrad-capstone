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

        def end(self, **kw):
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


def test_trace_steps_are_laid_out_on_a_timeline() -> None:
    """Traces are built after the answer; each step gets its recorded duration, in order, and
    the root spans the question's wall time (not 0 s, as before Day 14)."""
    from types import SimpleNamespace

    from src.tracing import LangfuseTracer

    class Obs:
        def __init__(self, name, log):
            self.name, self.log = name, log
            self._otel_span = SimpleNamespace(_start_time=None)

        def start_observation(self, **kw):
            return Obs(kw["name"], self.log)

        def end(self, end_time=None):
            self.log.append((self.name, self._otel_span._start_time, end_time))

    log: list = []
    root = Obs("root", log)
    children = [
        {"name": "guard", "as_type": "guardrail", "output": {}},
        {"name": "intake", "as_type": "generation", "raw": {"ms": 5000}},
        {
            "name": "tools",
            "as_type": "chain",
            "children": [{"name": "compute_duty_excise", "as_type": "tool"}],
        },
        {"name": "search_regulations", "as_type": "retriever", "output": {"ms": 2000}},
        {"name": "writer", "as_type": "generation", "raw": {"ms": 3000}},
    ]
    LangfuseTracer.__new__(LangfuseTracer).lay_out(root, children, seconds=12.0)
    t0 = root._otel_span._start_time
    span = {n: ((s - t0) / 1e9, (e - s) / 1e9) for n, s, e in log}
    starts = [
        span[n][0] for n in ("guard", "intake", "tools", "search_regulations", "writer")
    ]
    assert starts == sorted(starts) and len(set(starts)) == 5  # the order they ran in
    assert span["intake"] == (0.001, 5.0)
    assert span["writer"][1] == 3.0 and span["search_regulations"][1] == 2.0
    assert span["guard"][1] == 0.001  # an untimed step takes 1 ms
    assert (
        span["tools"][0]
        <= span["compute_duty_excise"][0]
        < span["search_regulations"][0]
    )
