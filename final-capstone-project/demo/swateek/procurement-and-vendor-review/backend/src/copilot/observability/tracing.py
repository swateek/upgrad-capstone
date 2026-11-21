"""Langfuse tracing (Track B: trace dashboard of real query executions).

One agent turn = one Langfuse trace: an `agent` observation named after the domain, with the
LangChain callback handler attached so every model call (planner, executor, critic) and tool
call nests under it. Session id = the conversation's thread id. Tags carry domain, provider and
any caller tags (e.g. eval query ids).

Disabled unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set. Everything sent is passed
through the same PII scrubber as the corpus, so an email or phone number typed into the chat is
redacted before it leaves the process. Keys come from Settings (.env), never from code.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from copilot.config import Settings
from copilot.ingest.pii import scrub

log = logging.getLogger(__name__)


def _mask(*, data: Any, **_: Any) -> Any:
    if isinstance(data, str):
        return scrub(data)[0]
    if isinstance(data, dict):
        return {k: _mask(data=v) for k, v in data.items()}
    if isinstance(data, list | tuple):
        return [_mask(data=v) for v in data]
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
                mask=_mask,
            )
        except Exception as err:  # noqa: BLE001 - tracing must never break the app
            log.warning("tracing disabled: %s", err)
            self.enabled = False

    @contextmanager
    def run(
        self,
        name: str,
        session_id: str,
        question: str,
        tags: list[str],
        metadata: dict[str, str] | None = None,
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
                session_id=session_id, tags=tags, trace_name=name, metadata=metadata or {}
            ),
        ):
            run = TraceRun(observation=obs, callbacks=[CallbackHandler(public_key=self.public_key)])
            try:
                run.url = self.client.get_trace_url()
            except Exception:  # noqa: BLE001
                run.url = None
            yield run

    def flush(self) -> None:
        if self.client is not None:
            self.client.flush()
