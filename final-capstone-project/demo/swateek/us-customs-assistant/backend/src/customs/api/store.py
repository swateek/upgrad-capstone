"""Small key-value store for rate limits and the answer cache: Redis when REDIS_URL is set
(Docker), else in-process (single worker, plan §4.6). Nothing durable is kept here."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Protocol

log = logging.getLogger(__name__)


class KV(Protocol):
    name: str

    def get_json(self, key: str) -> Any | None: ...
    def set_json(self, key: str, value: Any, ttl_s: int) -> None: ...
    def hit(self, key: str, window_s: int) -> int: ...


class MemoryKV:
    """TTL'd JSON values (bounded LRU) and fixed-window counters, for one process."""

    name = "memory"

    def __init__(self, max_items: int = 2000, clock=time.time) -> None:
        self._values: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._counters: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()
        self._max = max_items
        self._clock = clock

    def get_json(self, key: str) -> Any | None:
        with self._lock:
            item = self._values.get(key)
            if item is None:
                return None
            expires, raw = item
            if expires < self._clock():
                del self._values[key]
                return None
            self._values.move_to_end(key)
            return json.loads(raw)

    def set_json(self, key: str, value: Any, ttl_s: int) -> None:
        with self._lock:
            self._values[key] = (self._clock() + ttl_s, json.dumps(value))
            self._values.move_to_end(key)
            while len(self._values) > self._max:
                self._values.popitem(last=False)

    def hit(self, key: str, window_s: int) -> int:
        """Count one hit in the current window; returns the count so far."""
        bucket = int(self._clock() // window_s)
        with self._lock:
            b, n = self._counters.get(key, (bucket, 0))
            n = n + 1 if b == bucket else 1
            self._counters[key] = (bucket, n)
            if len(self._counters) > 10 * self._max:
                self._counters = {k: v for k, v in self._counters.items() if v[0] == bucket}
            return n


class RedisKV:
    name = "redis"

    def __init__(self, url: str) -> None:
        import redis

        self.r = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)

    def get_json(self, key: str) -> Any | None:
        raw = self.r.get(key)
        return None if raw is None else json.loads(raw)

    def set_json(self, key: str, value: Any, ttl_s: int) -> None:
        self.r.set(key, json.dumps(value), ex=ttl_s)

    def hit(self, key: str, window_s: int) -> int:
        k = f"{key}:{int(time.time() // window_s)}"
        pipe = self.r.pipeline()
        pipe.incr(k)
        pipe.expire(k, window_s * 2)
        return int(pipe.execute()[0])


def make_kv(redis_url: str | None) -> KV:
    if redis_url:
        try:
            kv = RedisKV(redis_url)
            kv.r.ping()
            return kv
        except Exception as err:  # noqa: BLE001 - fall back rather than fail the app
            log.warning("redis unavailable (%s); using the in-process store", type(err).__name__)
    return MemoryKV()
