"""Track B retry policy and a client-side rate/concurrency gate.

Retry 429 and 503 after 2 s, 4 s, 8 s, then stop. Never retry 400/401/404.
Failures are logged with provider, URL, status and UTC time. The API key is never logged.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Self

import openai

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 503}


class RateGate:
    """Caps concurrent requests and requests per rolling minute, per process."""

    def __init__(self, max_concurrency: int, requests_per_minute: int) -> None:
        self._sem = threading.BoundedSemaphore(max_concurrency)
        self._rpm = requests_per_minute
        self._stamps: deque[float] = deque()
        self._lock = threading.Lock()

    def _wait_for_rate_slot(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._stamps and now - self._stamps[0] >= 60.0:
                    self._stamps.popleft()
                if len(self._stamps) < self._rpm:
                    self._stamps.append(now)
                    return
                sleep_for = 60.0 - (now - self._stamps[0])
            time.sleep(max(sleep_for, 0.05))

    def __enter__(self) -> Self:
        self._sem.acquire()
        try:
            self._wait_for_rate_slot()
        except BaseException:
            self._sem.release()
            raise
        return self

    def __exit__(self, *exc: object) -> None:
        self._sem.release()


def _status_of(err: Exception) -> int | None:
    if isinstance(err, openai.APIStatusError):
        return err.status_code
    return None


def call_with_retry[T](
    fn: Callable[[], T],
    *,
    provider: str,
    url: str,
    delays: Sequence[float] = (2.0, 4.0, 8.0),
    gate: RateGate | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    attempts = len(delays) + 1
    for attempt in range(attempts):
        try:
            if gate is None:
                return fn()
            with gate:
                return fn()
        except (openai.APIStatusError, openai.APIConnectionError) as err:
            status = _status_of(err)
            log.warning(
                "llm call failed provider=%s url=%s status=%s attempt=%d/%d at=%s",
                provider,
                url,
                status if status is not None else "connection",
                attempt + 1,
                attempts,
                datetime.now(UTC).isoformat(timespec="seconds"),
            )
            retryable = status in RETRYABLE_STATUS
            if not retryable or attempt == attempts - 1:
                raise
            sleep(delays[attempt])
    raise AssertionError("unreachable")
