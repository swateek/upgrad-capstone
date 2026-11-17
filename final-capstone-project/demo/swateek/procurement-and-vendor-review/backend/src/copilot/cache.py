"""A tiny key-value store for the retrieval cache and rate limits.

Redis when REDIS_URL is set (Docker), otherwise an in-process fallback (dev, tests; correct
only for a single worker). Both offer the same three operations.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from typing import Any

from copilot.config import Settings


class Store:
    def get(self, key: str) -> Any | None:
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl_s: int) -> None:
        raise NotImplementedError

    def hit(self, key: str, window_s: int) -> tuple[int, int]:
        """Count one event in a fixed window; return (count so far, seconds left in window)."""
        raise NotImplementedError


class MemoryStore(Store):
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if item is None or item[0] < time.time():
                self._data.pop(key, None)
                return None
            return item[1]

    def set(self, key: str, value: Any, ttl_s: int) -> None:
        with self._lock:
            self._data[key] = (time.time() + ttl_s, value)

    def hit(self, key: str, window_s: int) -> tuple[int, int]:
        now = time.time()
        with self._lock:
            expires, count = self._data.get(key, (0.0, 0))
            if expires < now:
                expires, count = now + window_s, 0
            count += 1
            self._data[key] = (expires, count)
            return count, max(1, int(expires - now))


class RedisStore(Store):
    def __init__(self, url: str) -> None:
        import redis

        self.r = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)

    def get(self, key: str) -> Any | None:
        raw = self.r.get(key)
        return None if raw is None else json.loads(raw)

    def set(self, key: str, value: Any, ttl_s: int) -> None:
        self.r.set(key, json.dumps(value), ex=ttl_s)

    def hit(self, key: str, window_s: int) -> tuple[int, int]:
        pipe = self.r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_s, nx=True)
        pipe.ttl(key)
        count, _, ttl = pipe.execute()
        return int(count), max(1, int(ttl))


def make_store(settings: Settings) -> Store:
    return RedisStore(settings.redis_url) if settings.redis_url else MemoryStore()


_SPACES = re.compile(r"\s+")


def normalize_query(q: str) -> str:
    return _SPACES.sub(" ", q.strip().lower()).strip(" ?.!")


def cache_key(*parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str)
    return "ret:" + hashlib.sha256(blob.encode()).hexdigest()
