"""Oracle run on the DEV set, offline: the graph with a scripted "perfect" model.

The intake returns the gold facts (minus the gold clarify fields on a clarify turn), the planner
returns the router's plan, the writer words the bottom line with the right handles. Retrieval
returns nothing, so every source comes from the fetch-by-id fallback. What is left to fail is
everything that is not the model: guard, scope, clarify, calculators, escalation, citations.
It is the pipeline's ceiling on dev, scored with eval.score exactly as the real runs will be.

    uv run python -m eval.oracle_dev
"""

from __future__ import annotations

import json
import re

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from openai import OpenAI

from customs.agent.graph import CustomsAgent
from customs.agent.intake import to_intake
from customs.agent.planner import plan_json, router_plan
from customs.config import PROJECT_ROOT, get_settings
from customs.llm.chat import ChatClient
from customs.observability.tracing import Tracer
from customs.retrieval.service import RegulationSearch
from customs.tools.calc import new_case, step_normalise, step_restrictions
from customs.tools.models import Line, Profile
from customs.tools.tables import load_tables
from eval.score import score_turn

DEV = PROJECT_ROOT / "pack" / "eval" / "dev.jsonl"
DROP = {"age_21_plus": ["age"], "exemption_used_last_30_days": ["exemption_used_last_30_days"],
        "trip_hours_or_arrived_from_mexico": ["trip_hours"], "arrival_state": ["arrival_state"],
        "value_usd_of_line": [], "origin_country_of_line": []}  # fmt: skip


def turn_facts(facts: dict, gold_turn: dict) -> dict:
    f = json.loads(json.dumps(facts))
    for field in gold_turn.get("clarify_fields", []):
        for k in DROP.get(field, []):
            f["profile"].pop(k, None)
        if field == "origin_country_of_line":
            for ln in f["basket"]:
                ln.pop("origin", None)
    return f


class Oracle:
    def __init__(self) -> None:
        self.facts: dict = {}
        self.tables = load_tables()

    def reply(self, body: dict) -> dict:
        system = body["messages"][0]["content"]
        user = body["messages"][-1]["content"]
        if "Extract the traveller's facts" in system:
            return {"profile": to_intake(self.facts["profile"]), "basket": self.facts["basket"]}
        if "You plan the calculation" in system:
            f = self.facts
            case = new_case(Profile.model_validate(f["profile"]),
                            [Line.model_validate(x) for x in f["basket"]], self.tables)  # fmt: skip
            step_normalise(case)
            step_restrictions(case)
            return {"steps": plan_json(router_plan(case))}
        if "You write the answer card" in system:
            kind = re.search(r"Outcome: (\w+)", user).group(1)
            figs = dict(re.findall(r"(F\d+) ([^=;]+?) =", user))
            total = next((h for h, lab in figs.items() if lab.strip() == "total you owe"), None)
            total = total or next(
                (h for h, lab in figs.items() if "total federal excise" in lab), None
            )
            s1 = "[S1]" if "S1 " in user else ""
            bl = {
                "owe": f"You'll owe about [{total}].",
                "mixed": f"Some items can't come in, and you'll owe about [{total}]."
                if total
                else "No: some items can't come in, and others are over the allowance.",
                "nothing_owed": "You owe nothing.",
                "prohibited": "No, it can't come in.",
                "seizure_risk": "The tobacco over the allowance may be seized.",
            }.get(kind, "See below.")
            return {"bottom_line": bl, "working": [f"This follows the rules {s1}".strip() + "."]
                    if s1 else []}  # fmt: skip
        if "You check an answer" in system:
            return {"items": []}
        raise AssertionError("unexpected prompt")

    def handler(self, request: httpx.Request) -> httpx.Response:
        content = json.dumps(self.reply(json.loads(request.content)))
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "oracle",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})  # fmt: skip


def run(verbose: bool = True) -> tuple[int, int]:
    s = get_settings().model_copy(update={"langfuse_public_key": None})
    oracle = Oracle()
    client = OpenAI(base_url="https://oracle.test/v1", api_key="x", max_retries=0,
                    http_client=httpx.Client(transport=httpx.MockTransport(oracle.handler)))  # fmt: skip
    t = load_tables()
    agent = CustomsAgent(
        s, chat=ChatClient(s, client=client),
        search=RegulationSearch(s, rankings=lambda qs, fs: [[] for _ in qs], tables=t),
        checkpointer=InMemorySaver(), tracer=Tracer(s), tables=t,
    )  # fmt: skip
    total = right = 0
    for line in DEV.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        for i, text in enumerate(row["turns"]):
            gold = row["gold"][i]
            oracle.facts = turn_facts(row["facts"], gold)
            card = agent.ask(f"oracle-{row['id']}", text, mode="planner")
            pred = {"outcome": card["outcome"], "kind": card["kind"], "owe_usd": card["owe_usd"],
                    "citations": card["citations"]}  # fmt: skip
            sc = score_turn(pred, gold)
            total += 1
            right += sc.correct
            mark = "ok " if sc.correct else "BAD"
            if verbose or not sc.correct:
                print(f"{mark} {row['id']} t{i + 1} {row['category']:28s} gold {gold['outcome']}/"
                  f"{gold['bottom_line']['kind']} {gold['bottom_line'].get('owe_usd')} | got "
                  f"{card['outcome']}/{card['kind']} {card['owe_usd']} {sc.labels} "
                  f"{card['meta'].get('escalation', '')} {card['meta'].get('detail', '')}")  # fmt: skip
    return right, total


def main() -> None:
    right, total = run()
    print(f"\noracle on dev: {right}/{total} turns correct")


if __name__ == "__main__":
    main()
