"""The only way this project calls a model.

Every chat and embeddings request goes through `LLM`, which:

- queues requests so each endpoint has one request in flight (first come,
  first served, across threads and across processes on the same machine);
- retries 429 / 5xx / connection errors with exponential back-off and jitter,
  honouring `Retry-After`; other 4xx errors fail at once;
- refuses calls that would exceed the endpoint limits (8,192 tokens per call,
  1,024 output) before sending them;
- caches responses in `logs/llm_cache.sqlite3` (turn off for official runs);
- writes one line per call to `logs/usage.jsonl` (no prompts, no keys).

Usage:

    from src.llm import LLM
    llm = LLM.from_env(run_name="dev")
    r = llm.chat([{"role": "user", "content": "Say OK."}], stage="smoke", max_tokens=5)
    r.content, r.usage.prompt_tokens, r.cached
    vectors = llm.embed(["text one", "text two"], stage="index")

Settings (environment or `.env`): see `src/endpoints.py`, plus
    LLM_CACHE=0            disable the cache (official runs)
    LLM_RUN_NAME=<name>    default run name written to usage.jsonl
    LLM_LOG_DIR=<path>     where usage.jsonl and the cache live (default customs-agent/logs)
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import math
import os
import random
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import openai

from src.endpoints import PROJECT_ROOT, ConfigError, Endpoint, load_env, make_client

try:  # cross-process lock; available on macOS and Linux
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

# Endpoint limits (docs/endpoint_check.md, README)
MAX_CALL_TOKENS = 8192
MAX_OUTPUT_TOKENS = 1024
CHARS_PER_TOKEN = (
    3.5  # conservative estimate for English + JSON; real counts come from `usage`
)

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


# ----------------------------------------------------------------- errors
class LLMError(RuntimeError):
    """A call failed after all retries, or failed with a non-retryable error."""

    def __init__(
        self, message: str, *, stage: str, status: int | None = None, attempts: int = 1
    ):
        super().__init__(message)
        self.stage = stage
        self.status = status
        self.attempts = attempts


class BudgetError(ValueError):
    """A call would exceed the endpoint's token limits; it was not sent."""


# ----------------------------------------------------------------- results
@dataclass
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text from the model; parse and validate with Pydantic

    def args(self) -> dict[str, Any]:
        """Parsed arguments. Raises json.JSONDecodeError on malformed JSON."""
        return json.loads(self.arguments or "{}")


@dataclass
class ChatResult:
    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str | None
    usage: Usage
    model: str
    latency_ms: float
    cached: bool
    attempts: int

    def to_cache(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("cached")
        d.pop("latency_ms")
        d.pop("attempts")
        return d

    @classmethod
    def from_cache(cls, d: dict[str, Any], latency_ms: float) -> ChatResult:
        return cls(
            content=d["content"],
            tool_calls=[ToolCall(**t) for t in d["tool_calls"]],
            finish_reason=d["finish_reason"],
            usage=Usage(**d["usage"]),
            model=d["model"],
            latency_ms=latency_ms,
            cached=True,
            attempts=0,
        )


# ------------------------------------------------------------ queueing
class EndpointQueue:
    """One request in flight per endpoint, served in arrival order.

    Threads in this process take numbered tickets (FIFO). Across processes on
    the same machine, an exclusive lock on a file serialises callers, so a
    baseline run and an interactive session never overlap on the shared key.
    """

    def __init__(self, name: str, lock_dir: Path):
        self.name = name
        self._cond = threading.Condition()
        self._next_ticket = 0
        self._serving = 0
        self._lock_path = lock_dir / f".{name}.lock"

    @contextlib.contextmanager
    def slot(self) -> Iterator[float]:
        """Yields the time (ms) spent waiting for the slot."""
        t0 = time.perf_counter()
        with self._cond:
            ticket = self._next_ticket
            self._next_ticket += 1
            while ticket != self._serving:
                self._cond.wait()
        fh = None
        try:
            if fcntl is not None:
                self._lock_path.parent.mkdir(parents=True, exist_ok=True)
                fh = open(self._lock_path, "a+")  # noqa: SIM115 - held for the slot's lifetime
                fcntl.flock(fh, fcntl.LOCK_EX)
            yield (time.perf_counter() - t0) * 1000
        finally:
            if fh is not None:
                fcntl.flock(fh, fcntl.LOCK_UN)
                fh.close()
            with self._cond:
                self._serving += 1
                self._cond.notify_all()


# --------------------------------------------------------------- cache
class ResponseCache:
    """SQLite key-value cache, safe across threads and processes."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, created TEXT)"
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def get(self, key: str) -> Any | None:
        with contextlib.closing(self._connect()) as db:
            row = db.execute("SELECT value FROM cache WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, value: Any) -> None:
        with contextlib.closing(self._connect()) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO cache (key, value, created) VALUES (?, ?, ?)",
                (key, json.dumps(value), _now()),
            )


def cache_key(kind: str, payload: dict[str, Any]) -> str:
    blob = json.dumps(
        {"kind": kind, **payload}, sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(blob.encode()).hexdigest()


# ------------------------------------------------------------ helpers
def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds")


def estimate_tokens(obj: Any) -> int:
    """Rough upper estimate of input tokens, used only to refuse obviously oversized calls."""
    text = (
        obj
        if isinstance(obj, str)
        else json.dumps(obj, ensure_ascii=False, default=str)
    )
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def _status(e: Exception) -> int | None:
    return getattr(e, "status_code", None)


def _retry_after(e: Exception) -> float | None:
    resp = getattr(e, "response", None)
    headers = getattr(resp, "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _is_retryable(e: Exception) -> bool:
    if isinstance(e, (openai.APIConnectionError, openai.APITimeoutError)):
        return True
    return _status(e) in RETRYABLE_STATUS


# ------------------------------------------------------------------ LLM
@dataclass
class LLM:
    """Chat + embeddings client for both endpoints. Thread-safe."""

    chat_endpoint: Endpoint
    embed_endpoint: Endpoint
    run_name: str = "dev"
    cache_enabled: bool = True
    log_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "logs")
    max_attempts: int = 6
    base_delay: float = 1.0
    max_delay: float = 30.0
    embed_batch_size: int = 16  # the course embeddings endpoint rejects batches over 16 (HTTP 422)
    chat_client: Any = None  # injected in tests; built from the endpoint otherwise
    embed_client: Any = None
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        self.log_dir = Path(self.log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        if not self.chat_endpoint.model:
            raise ConfigError(
                "CHAT_MODEL is not set: add CHAT_MODEL=Qwen/Qwen3-8B to .env (see docs/endpoint_check.md)."
            )
        if not self.embed_endpoint.model:
            raise ConfigError(
                "EMBED_MODEL is not set (the embeddings server has no /v1/models)."
            )
        self.chat_client = self.chat_client or make_client(self.chat_endpoint)
        self.embed_client = self.embed_client or make_client(self.embed_endpoint)
        self._queues = {
            "chat": EndpointQueue("chat", self.log_dir),
            "embeddings": EndpointQueue("embeddings", self.log_dir),
        }
        self._cache = ResponseCache(self.log_dir / "llm_cache.sqlite3")
        self._log_lock = threading.Lock()
        self.usage_path = self.log_dir / "usage.jsonl"

    # ------------------------------------------------------------ setup
    @classmethod
    def from_env(cls, run_name: str | None = None, **overrides: Any) -> LLM:
        env_dir = load_env()
        chat = Endpoint.from_env("chat", "CHAT", env_dir)
        embed = Endpoint.from_env("embeddings", "EMBED", env_dir)
        kwargs: dict[str, Any] = {
            "run_name": run_name or os.environ.get("LLM_RUN_NAME", "dev"),
            "cache_enabled": os.environ.get("LLM_CACHE", "1") != "0",
        }
        if os.environ.get("LLM_LOG_DIR"):
            kwargs["log_dir"] = Path(os.environ["LLM_LOG_DIR"])
        kwargs.update(overrides)
        return cls(chat_endpoint=chat, embed_endpoint=embed, **kwargs)

    @property
    def chat_model(self) -> str:
        return self.chat_endpoint.model or ""

    @property
    def embed_model(self) -> str:
        return self.embed_endpoint.model or ""

    # ------------------------------------------------------------- chat
    def chat(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        stage: str,
        tools: Sequence[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
        seed: int | None = None,
        sample: int | None = None,
        extra_body: dict[str, Any] | None = None,
        cache: bool | None = None,
    ) -> ChatResult:
        """One chat completion.

        `stage` labels the call in usage.jsonl (e.g. "intake", "planner").
        `sample` makes repeated sampling cacheable: self-consistency sample 0, 1, 2
        get different cache entries. Calls with temperature > 0 and no `sample`
        or `seed` are not cached, since a cached sample would repeat itself.
        """
        if max_tokens > MAX_OUTPUT_TOKENS:
            raise BudgetError(
                f"{stage}: max_tokens={max_tokens} exceeds the {MAX_OUTPUT_TOKENS}-token output limit"
            )
        est_input = estimate_tokens(list(messages)) + (
            estimate_tokens(list(tools)) if tools else 0
        )
        if est_input + max_tokens > MAX_CALL_TOKENS:
            raise BudgetError(
                f"{stage}: about {est_input} input + {max_tokens} output tokens exceeds the "
                f"{MAX_CALL_TOKENS}-token call limit; shorten the prompt or retrieved context"
            )

        params: dict[str, Any] = {
            "model": self.chat_model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            params["tools"] = list(tools)
        if tool_choice is not None:
            params["tool_choice"] = tool_choice
        if response_format is not None:
            params["response_format"] = response_format
        if seed is not None:
            params["seed"] = seed
        if extra_body:
            params["extra_body"] = extra_body

        deterministic = temperature == 0 or seed is not None or sample is not None
        use_cache = self.cache_enabled if cache is None else cache
        use_cache = use_cache and deterministic
        key = cache_key("chat", {**params, "sample": sample}) if use_cache else None

        t0 = time.perf_counter()
        if key and (hit := self._cache.get(key)) is not None:
            result = ChatResult.from_cache(hit, (time.perf_counter() - t0) * 1000)
            self._log(
                "chat",
                stage,
                result.model,
                result.usage,
                result.latency_ms,
                cached=True,
                attempts=0,
            )
            return result

        resp, attempts, latency_ms, wait_ms = self._call(
            "chat", stage, lambda: self.chat_client.chat.completions.create(**params)
        )
        choice = resp.choices[0]
        msg = choice.message
        u = getattr(resp, "usage", None)
        result = ChatResult(
            content=msg.content,
            tool_calls=[
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments or "",
                )
                for tc in (msg.tool_calls or [])
            ],
            finish_reason=choice.finish_reason,
            usage=Usage(
                prompt_tokens=getattr(u, "prompt_tokens", None),
                completion_tokens=getattr(u, "completion_tokens", None),
                total_tokens=getattr(u, "total_tokens", None),
            ),
            model=getattr(resp, "model", None) or self.chat_model,
            latency_ms=latency_ms,
            cached=False,
            attempts=attempts,
        )
        if key:
            self._cache.put(key, result.to_cache())
        self._log(
            "chat",
            stage,
            result.model,
            result.usage,
            latency_ms,
            cached=False,
            attempts=attempts,
            wait_ms=wait_ms,
        )
        return result

    # ------------------------------------------------------- embeddings
    def embed(
        self, texts: Sequence[str], *, stage: str, cache: bool | None = None
    ) -> list[list[float]]:
        """Embeddings for each text, in order. Cached per text; misses are sent in batches."""
        texts = list(texts)
        use_cache = self.cache_enabled if cache is None else cache
        keys = [
            cache_key("embed", {"model": self.embed_model, "text": t}) for t in texts
        ]
        out: list[list[float] | None] = [None] * len(texts)

        if use_cache:
            for i, k in enumerate(keys):
                out[i] = self._cache.get(k)
            hits = sum(v is not None for v in out)
            if hits:
                self._log(
                    "embeddings",
                    stage,
                    self.embed_model,
                    Usage(),
                    0.0,
                    cached=True,
                    attempts=0,
                    extra={"inputs": hits},
                )

        missing = [i for i, v in enumerate(out) if v is None]
        for start in range(0, len(missing), self.embed_batch_size):
            idx = missing[start : start + self.embed_batch_size]
            batch = [texts[i] for i in idx]
            resp, attempts, latency_ms, wait_ms = self._call(
                "embeddings",
                stage,
                lambda batch=batch: self.embed_client.embeddings.create(
                    model=self.embed_model, input=batch
                ),
            )
            data = sorted(resp.data, key=lambda d: d.index)
            if len(data) != len(batch):
                raise LLMError(
                    f"{stage}: asked for {len(batch)} embeddings, got {len(data)}",
                    stage=stage,
                )
            for i, d in zip(idx, data, strict=True):
                vec = list(d.embedding)
                out[i] = vec
                if use_cache:
                    self._cache.put(keys[i], vec)
            u = getattr(resp, "usage", None)
            self._log(
                "embeddings",
                stage,
                self.embed_model,
                Usage(
                    prompt_tokens=getattr(u, "prompt_tokens", None),
                    completion_tokens=0,
                    total_tokens=getattr(u, "total_tokens", None),
                ),
                latency_ms,
                cached=False,
                attempts=attempts,
                wait_ms=wait_ms,
                extra={"inputs": len(batch)},
            )
        return [v for v in out if v is not None]

    # ---------------------------------------------------------- plumbing
    def _call(
        self, endpoint: str, stage: str, fn: Callable[[], Any]
    ) -> tuple[Any, int, float, float]:
        """Run `fn` in the endpoint's queue slot with retries. Returns (response, attempts, latency_ms, wait_ms)."""
        with self._queues[endpoint].slot() as wait_ms:
            attempt = 0
            while True:
                attempt += 1
                t0 = time.perf_counter()
                try:
                    resp = fn()
                    return resp, attempt, (time.perf_counter() - t0) * 1000, wait_ms
                except Exception as e:
                    status = _status(e)
                    if not _is_retryable(e) or attempt >= self.max_attempts:
                        self._log(
                            endpoint,
                            stage,
                            "",
                            Usage(),
                            (time.perf_counter() - t0) * 1000,
                            cached=False,
                            attempts=attempt,
                            wait_ms=wait_ms,
                            error=f"{type(e).__name__}:{status}",
                        )
                        why = (
                            "not retryable"
                            if not _is_retryable(e)
                            else f"gave up after {attempt} attempts"
                        )
                        raise LLMError(
                            f"{stage}: {endpoint} call failed ({why}): {type(e).__name__} {status or ''}",
                            stage=stage,
                            status=status,
                            attempts=attempt,
                        ) from e
                    delay = _retry_after(e)
                    if delay is None:
                        delay = random.uniform(
                            0, min(self.max_delay, self.base_delay * 2 ** (attempt - 1))
                        )
                    self.sleep(min(delay, self.max_delay))

    def _log(
        self,
        endpoint: str,
        stage: str,
        model: str,
        usage: Usage,
        latency_ms: float,
        *,
        cached: bool,
        attempts: int,
        wait_ms: float = 0.0,
        error: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Append one line to usage.jsonl. Never includes prompts, outputs or keys."""
        row = {
            "ts": _now(),
            "run": self.run_name,
            "stage": stage,
            "endpoint": endpoint,
            "model": model
            or (self.chat_model if endpoint == "chat" else self.embed_model),
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "latency_ms": round(latency_ms, 1),
            "queue_wait_ms": round(wait_ms, 1),
            "attempts": attempts,
            "cached": cached,
            "error": error,
            **(extra or {}),
        }
        line = json.dumps(row, ensure_ascii=False)
        with self._log_lock, open(self.usage_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


# ------------------------------------------------------------- smoke test
def _smoke() -> None:
    """`uv run python -m src.llm`: one chat call and one embeddings call against the real endpoints."""
    llm = LLM.from_env(run_name="smoke", cache_enabled=False)
    print(f"chat:       {llm.chat_endpoint}")
    print(f"embeddings: {llm.embed_endpoint}")
    r = llm.chat(
        [{"role": "user", "content": "Reply with the single word OK."}],
        stage="smoke",
        max_tokens=5,
    )
    print(
        f"chat -> {r.content!r} ({r.usage.prompt_tokens}+{r.usage.completion_tokens} tokens, {r.latency_ms:.0f} ms)"
    )
    vecs = llm.embed(["duty-free allowance for wine"], stage="smoke")
    print(f"embeddings -> {len(vecs)} vector(s) of {len(vecs[0])} dimensions")
    print(f"usage log: {llm.usage_path}")


if __name__ == "__main__":
    _smoke()
