"""Langfuse tracing in this app's own Langfuse project (plan D5, §8).

One question turn = one trace named `customs-agent`: an `agent` observation with the LangChain
callback handler attached, so every LangGraph node nests under it. Chat calls made through
customs.llm.chat are recorded as `generation` observations by `generation()`. Session id = the
conversation's thread id. Tags carry `customs`, `upgrad`, the agent mode and any caller tags
(eval run, category, question id).

Off unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set. Everything sent passes through
the PII scrubber first. Tracing must never break a request: every failure is logged and skipped.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from customs.config import Settings
from customs.ingest.pii import scrub

log = logging.getLogger(__name__)

TRACE_NAME = "customs-agent"


def mask(*, data: Any, **_: Any) -> Any:
    if isinstance(data, str):
        return scrub(data)[0]
    if isinstance(data, dict):
        return {k: mask(data=v) for k, v in data.items()}
    if isinstance(data, list | tuple):
        return [mask(data=v) for v in data]
    return data


@dataclass
class TraceRun:
    observation: Any = None
    callbacks: list[Any] = field(default_factory=list)
    url: str | None = None

    def finish(self, output: Any, metadata: dict[str, Any]) -> None:
        if self.observation is not None:
            self.observation.update(output=output, metadata=metadata)


class Tracer:
    def __init__(self, settings: Settings) -> None:
        pk = settings.langfuse_public_key
        sk = settings.langfuse_secret_key
        self.enabled = bool(pk and sk and settings.tracing_enabled)
        self.client = None
        self.public_key = pk
        if not self.enabled:
            return
        try:
            from langfuse import Langfuse

            self.client = Langfuse(
                public_key=pk,
                secret_key=sk.get_secret_value(),
                base_url=settings.langfuse_base_url,
                environment=settings.trace_environment,
                mask=mask,
            )
        except Exception as err:  # noqa: BLE001 - tracing must never break the app
            log.warning("tracing disabled: %s", err)
            self.enabled = False

    @contextmanager
    def run(
        self,
        session_id: str,
        question: str,
        tags: list[str],
        metadata: dict[str, str] | None = None,
        name: str = TRACE_NAME,
    ) -> Iterator[TraceRun]:
        if not self.enabled or self.client is None:
            yield TraceRun()
            return
        from langfuse import propagate_attributes
        from langfuse.langchain import CallbackHandler

        with (
            self.client.start_as_current_observation(
                as_type="agent", name=name, input=question
            ) as obs,
            propagate_attributes(
                session_id=session_id,
                tags=["customs", "upgrad", *tags],
                trace_name=name,
                metadata=metadata or {},
            ),
        ):
            run = TraceRun(observation=obs, callbacks=[CallbackHandler(public_key=self.public_key)])
            try:
                run.url = self.client.get_trace_url()
            except Exception:  # noqa: BLE001
                run.url = None
            yield run

    @contextmanager
    def generation(self, name: str, model: str, messages: list[dict[str, Any]]) -> Iterator[Any]:
        """Wrap one chat call; the caller updates it with output and usage."""
        if not self.enabled or self.client is None:
            yield None
            return
        with self.client.start_as_current_observation(
            as_type="generation", name=name, model=model, input=messages
        ) as gen:
            yield gen

    def score(self, name: str, value: float | str, comment: str | None = None) -> None:
        """Score the current trace (verifier_passed, outcome, correct, ...)."""
        if not self.enabled or self.client is None:
            return
        try:
            self.client.score_current_trace(name=name, value=value, comment=comment)
        except Exception as err:  # noqa: BLE001
            log.warning("score %s not recorded: %s", name, err)

    def flush(self) -> None:
        if self.client is not None:
            self.client.flush()
