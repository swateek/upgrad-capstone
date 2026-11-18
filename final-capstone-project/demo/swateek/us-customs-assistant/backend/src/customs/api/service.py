"""The API's agent service (plan §9, §13): progress, queueing, rate limits, answer cache,
session purge, and fact edits. It wraps the frozen agent without changing it.

- Progress: the agent passes the tracer's LangChain callbacks into the graph, so a tracer that
  adds a node-start handler reports each node as it starts ("Running the calculators...").
- Queue: one question runs at a time (the course key serves one request at a time); a question
  that has to wait gets a `queued` event first.
- Answer cache (first turns only; off for evals): a hit returns the stored card and seeds the
  new thread with the stored state, so a follow-up or correction works exactly as live.
- Fact edits from the card become a correction message, the same path the corrections suite
  measures, so the agent behind the UI is the agent that was evaluated.
"""

from __future__ import annotations

import hashlib
import queue
import re
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import yaml
from langchain_core.callbacks import BaseCallbackHandler

from customs.api.sessions import Sessions
from customs.api.store import KV, make_kv
from customs.config import PROJECT_ROOT, Settings
from customs.ingest.pii import scrub
from customs.observability.tracing import Tracer

THREAD_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
NODE_LABELS = {
    "guard": "Checking the question",
    "rag": "Searching the regulations",
    "intake": "Reading your trip and what you bought",
    "prepare": "Checking what applies",
    "clarify": "Checking what we still need",
    "plan": "Planning the calculation",
    "execute": "Running the calculators",
    "audit": "Checking the results and finding the regulations",
    "write": "Writing the answer",
    "verify": "Verifying every figure and source",
}
CACHEABLE = {"answered", "clarify", "refused", "out_of_scope"}


class RateLimited(Exception):
    def __init__(self, what: str) -> None:
        super().__init__(what)
        self.what = what


def agent_version() -> str:
    lock = PROJECT_ROOT / "pack" / "agent.lock.yaml"
    if not lock.exists():
        return "unfrozen"
    return f"v{yaml.safe_load(lock.read_text(encoding='utf-8'))['version']}"


# --- progress ------------------------------------------------------------------------------------


class NodeProgress(BaseCallbackHandler):
    """Reports each graph node as it starts (not its nested runs)."""

    def __init__(self, emit) -> None:
        self.emit = emit
        self.last: str | None = None

    def on_chain_start(self, serialized, inputs, **kwargs: Any) -> None:
        node = (kwargs.get("metadata") or {}).get("langgraph_node")
        if node and kwargs.get("name") == node and node != self.last:
            self.last = node
            self.emit({"event": "node", "node": node, "label": NODE_LABELS.get(node, node)})


class ProgressTracer(Tracer):
    """Langfuse tracing as usual, plus node progress for the request on this worker thread."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.local = threading.local()

    @contextmanager
    def run(self, *args: Any, **kwargs: Any):
        with super().run(*args, **kwargs) as tr:
            emit = getattr(self.local, "emit", None)
            if emit is not None:
                tr.callbacks = [*tr.callbacks, NodeProgress(emit)]
            yield tr


# --- fact edits ----------------------------------------------------------------------------------


def correction_message(profile: dict[str, Any], lines: dict[int, dict[str, Any]],
                       basket: list[dict]) -> str:  # fmt: skip
    """Edits from the card's 'facts relied on', written as the traveller would say them."""
    said = []
    if "age" in profile:
        said.append(f"I am {profile['age']} years old.")
    if "trip_hours" in profile:
        said.append(f"I was away {float(profile['trip_hours']):g} hours.")
    if "arrived_directly_from" in profile:
        said.append(f"I came back directly from {profile['arrived_directly_from']}.")
    if "exemption_used_last_30_days" in profile:
        used = profile["exemption_used_last_30_days"]
        said.append(
            f"I have {'' if used else 'not '}used my duty-free exemption in the last 30 days."
        )
    if "arrival_state" in profile:
        said.append(f"I land in {profile['arrival_state']}.")
    for n in sorted(lines):
        e = lines[n]
        item = (basket[n - 1].get("item", "item") if 0 < n <= len(basket) else "item").replace(
            "_", " "
        )
        bits = []
        if "quantity" in e:
            bits.append(f"there are {float(e['quantity']):g} of them")
        if "container_ml" in e:
            bits.append(f"each is {float(e['container_ml']):g} ml")
        if "abv" in e:
            bits.append(f"it is {float(e['abv']):g}% alcohol")
        if "value_usd" in e:
            bits.append(f"I paid ${float(e['value_usd']):,.2f} in total")
        if "origin" in e:
            bits.append(f"it was made in {e['origin']}")
        if bits:
            said.append(f"Item {n} ({item}): " + "; ".join(bits) + ".")
    return "Correction to my facts: " + " ".join(said)


# --- the service ---------------------------------------------------------------------------------


SERVED_MODES = ("planner", "router")


class AgentService:
    def __init__(self, settings: Settings, agent=None, kv: KV | None = None,
                 sessions: Sessions | None = None) -> None:  # fmt: skip
        if settings.agent_mode not in SERVED_MODES:
            # tool_calling and single_rag are ablations for the eval runner only: plain RAG
            # repeats planted instructions from retrieved text (safety probes 18 Nov)
            raise ValueError(f"AGENT_MODE={settings.agent_mode!r}: the app serves {SERVED_MODES}")
        self.settings = settings
        self._agent = agent
        self.kv = kv or make_kv(settings.redis_url)
        self.busy = threading.Lock()
        self.version = agent_version()
        self._sessions = sessions

    @property
    def agent(self):
        if self._agent is None:
            from customs.agent.graph import CustomsAgent

            self._agent = CustomsAgent(self.settings, tracer=ProgressTracer(self.settings))
        return self._agent

    @property
    def sessions(self) -> Sessions:
        if self._sessions is None:
            self._sessions = Sessions(
                self.settings.data_dir / "state" / "sessions.sqlite",
                self.settings.session_ttl_s,
                self.agent.checkpointer.delete_thread,
            )
        return self._sessions

    # --- limits and cache -----------------------------------------------------------------
    def check_limits(self, thread_id: str, client: str) -> None:
        if self.kv.hit(f"rl:ip:{client}", 60) > self.settings.rate_limit_ip_per_min:
            raise RateLimited("Too many requests from this client; try again in a minute.")
        if self.kv.hit(f"rl:chat:{thread_id}", 60) > self.settings.rate_limit_chat_per_min:
            raise RateLimited("Too many questions in this conversation; try again in a minute.")

    @property
    def cache_ttl_s(self) -> int:
        # a cached conversation must not outlive the session purge (plan §7)
        return min(self.settings.retrieval_cache_ttl_s, self.settings.session_ttl_s)

    def cacheable(self, message: str) -> bool:
        """Questions carrying personal data are never cached (they would sit in Redis)."""
        return self.settings.answer_cache_enabled and not scrub(message)[1]

    def cache_key(self, message: str) -> str:
        norm = " ".join(message.lower().split())
        raw = f"{self.version}|{self.settings.agent_mode}|{norm}"
        return "answer:" + hashlib.sha256(raw.encode()).hexdigest()

    # --- conversations --------------------------------------------------------------------
    def new_thread_id(self) -> str:
        return uuid.uuid4().hex

    def thread(self, thread_id: str) -> dict[str, Any] | None:
        if not self.sessions.known(thread_id):
            return None
        st = self.agent.state(thread_id)
        if not st:
            return None
        return {"thread_id": thread_id, "facts": st.get("facts"), "history": st.get("history", []),
                "card": st.get("card")}  # fmt: skip

    def ask(self, thread_id: str, message: str, client: str) -> Iterator[dict[str, Any]]:
        """Events for one question: queued?, node..., then card (or error)."""
        self.sessions.purge()
        first_turn = not self.sessions.known(thread_id)
        self.sessions.touch(thread_id)
        key = self.cache_key(message)
        if first_turn and self.cacheable(message):
            hit = self.kv.get_json(key)
            if hit is not None:
                self.agent.graph.update_state({"configurable": {"thread_id": thread_id}},
                                              hit["state"], as_node="verify")  # fmt: skip
                card = hit["card"] | {"meta": {**hit["card"].get("meta", {}), "cached": True}}
                yield {"event": "card", "thread_id": thread_id, "card": card}
                return
        events: queue.Queue = queue.Queue()

        def work() -> None:
            tracer = getattr(self.agent, "tracer", None)
            if isinstance(tracer, ProgressTracer):
                tracer.local.emit = events.put
            try:
                if self.busy.locked():
                    events.put({"event": "queued"})
                with self.busy:
                    events.put({"event": "started"})
                    card = self.agent.ask(thread_id, message, tags=["ui"])
                events.put({"event": "card", "thread_id": thread_id, "card": card})
            except Exception as err:  # noqa: BLE001 - reported to the client, not raised
                events.put({"event": "error", "detail": "Something went wrong answering this.",
                            "kind": type(err).__name__})  # fmt: skip
            finally:
                if isinstance(tracer, ProgressTracer):
                    tracer.local.emit = None

        threading.Thread(target=work, daemon=True).start()
        while True:
            ev = events.get()
            if ev["event"] == "card" and first_turn and self.cacheable(message):
                card = ev["card"]
                if card.get("outcome") in CACHEABLE:
                    state = {k: v for k, v in self.agent.state(thread_id).items()
                             if k in ("history", "facts", "asked", "asked_fields", "plan",
                                      "answered", "card", "message", "plan_source")}  # fmt: skip
                    self.kv.set_json(key, {"card": card, "state": state}, self.cache_ttl_s)
            yield ev
            if ev["event"] in ("card", "error"):
                return
