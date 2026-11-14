"""Provider profiles. PROVIDER picks where chat, embeddings and rerank run; nothing else in the
code checks the provider name.

    siliconflow  chat Qwen3-8B, Qwen3-Embedding-0.6B, Qwen3-Reranker-8B, all on SiliconFlow
    upgrad       chat Qwen3-8B on the course endpoint (group 031-045), bge-small-en-v1.5 on the
                 course embedding endpoint. The course has no reranker, so Qwen3-8B on the same
                 chat endpoint orders the candidates (UPGRAD_RERANKER=upgrad), or none. Nothing
                 under upgrad calls SiliconFlow.

The course endpoints use their own CA certificates; TLS verification is always on. Every
request to an endpoint passes one process-wide gate (copilot.llm.retry), so the course key's
limit of one active request holds for the agent, the critic and the evals alike.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx
from openai import OpenAI

from copilot.config import Settings
from copilot.llm.retry import GatedTransport, shared_gate

QWEN_EMBEDDING = "Qwen/Qwen3-Embedding-0.6B"
QWEN_RERANKER = "Qwen/Qwen3-Reranker-8B"
BGE_EMBEDDING = "bge-small-en-v1.5"
BGE_TOKENIZER = "BAAI/bge-small-en-v1.5"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Course limits (Track B guide; embedding quickstart).
UPGRAD_CHAT_CONCURRENCY = 1  # one active request per group key
UPGRAD_EMBED_BATCH = 16
UPGRAD_EMBED_MAX_TOKENS = 512


class ProviderNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class Endpoint:
    """One HTTP endpoint: where, with which key and CA, and how many requests at once."""

    name: str  # for logs and traces, e.g. "upgrad-chat"
    base_url: str
    api_key: str = field(repr=False)
    ca_cert: Path | None  # None: the system trust store
    max_concurrency: int
    requests_per_minute: int


@dataclass(frozen=True)
class ProviderConfig(Endpoint):
    """Chat."""

    model: str = ""
    extra_body: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingConfig(Endpoint):
    model: str = ""
    batch_size: int = 32
    max_tokens: int | None = None  # per text; longer texts are embedded in windows
    tokenizer_id: str | None = None  # for windowing; needed when max_tokens is set
    query_style: Literal["qwen", "bge"] = "qwen"
    # Qdrant collection = <domain>__<chunker>[__<suffix>]. SiliconFlow keeps the original
    # unsuffixed name, so its existing index is used as-is and never rebuilt.
    collection_suffix: str | None = None


@dataclass(frozen=True)
class RerankConfig(Endpoint):
    model: str = ""
    # rerank_api: a cross-encoder behind /rerank (SiliconFlow).
    # chat_listwise: the chat model orders the candidates in one call (copilot.retrieval.rerank).
    kind: Literal["rerank_api", "chat_listwise"] = "rerank_api"
    extra_body: dict[str, Any] = field(default_factory=dict)


def _key(value: Any, var: str) -> str:
    if value is None or not value.get_secret_value().strip():
        raise ProviderNotConfigured(f"{var} is not set. Add it to .env (see env.sample).")
    return value.get_secret_value().strip()


def _cert(settings: Settings, path: Path, var: str) -> Path:
    p = settings.resolve(path)
    if not p.is_file():
        raise ProviderNotConfigured(f"{var} points to {p}, which does not exist.")
    return p


def _siliconflow(settings: Settings, name: str) -> dict[str, Any]:
    return {
        "name": name,
        "base_url": settings.siliconflow_base_url,
        "api_key": _key(settings.siliconflow_api_key, "SILICONFLOW_API_KEY"),
        "ca_cert": None,
        "max_concurrency": settings.max_concurrency,
        "requests_per_minute": settings.requests_per_minute,
    }


def get_provider(settings: Settings, provider: str | None = None) -> ProviderConfig:
    """Chat endpoint of the active provider (or of `provider`, e.g. the judge's siliconflow)."""
    which = provider or settings.provider
    if which == "siliconflow":
        return ProviderConfig(
            **_siliconflow(settings, "siliconflow"),
            model=settings.chat_model,
            extra_body={"enable_thinking": settings.enable_thinking},
        )
    if which == "upgrad":
        return ProviderConfig(
            name="upgrad",
            base_url=settings.upgrad_chat_base_url,
            api_key=_key(settings.upgrad_chat_api_key, "UPGRAD_CHAT_API_KEY"),
            ca_cert=_cert(settings, settings.upgrad_chat_ca_cert, "UPGRAD_CHAT_CA_CERT"),
            max_concurrency=UPGRAD_CHAT_CONCURRENCY,
            requests_per_minute=settings.requests_per_minute,
            model=settings.chat_model,
            # vLLM-style switch for Qwen3's thinking mode (checked by copilot.llm.probe)
            extra_body={"chat_template_kwargs": {"enable_thinking": settings.enable_thinking}},
        )
    raise ProviderNotConfigured(f"Unknown provider: {which}")


def get_embedding(settings: Settings) -> EmbeddingConfig:
    if settings.provider == "siliconflow":
        return EmbeddingConfig(
            **_siliconflow(settings, "siliconflow-embed"),
            model=QWEN_EMBEDDING,
            batch_size=32,  # SiliconFlow: "the maximum array size is 32"
            query_style="qwen",
        )
    return EmbeddingConfig(
        name="upgrad-embed",
        base_url=settings.upgrad_embed_base_url,
        api_key=_key(settings.upgrad_embed_api_key, "UPGRAD_EMBED_API_KEY"),
        ca_cert=_cert(settings, settings.upgrad_embed_ca_cert, "UPGRAD_EMBED_CA_CERT"),
        max_concurrency=1,  # shared by every group; one batch at a time
        requests_per_minute=settings.requests_per_minute,
        model=BGE_EMBEDDING,
        batch_size=UPGRAD_EMBED_BATCH,
        max_tokens=UPGRAD_EMBED_MAX_TOKENS,
        tokenizer_id=BGE_TOKENIZER,
        query_style="bge",
        collection_suffix="bge-small-en-v1-5",
    )


def siliconflow_reranker(settings: Settings, model: str = QWEN_RERANKER) -> RerankConfig:
    return RerankConfig(**_siliconflow(settings, "siliconflow-rerank"), model=model)


def get_reranker(settings: Settings) -> RerankConfig | None:
    """siliconflow: Qwen3-Reranker-8B. upgrad: Qwen3-8B on the course chat endpoint, listwise
    (it shares the chat endpoint's gate), or None with UPGRAD_RERANKER=none."""
    if settings.provider == "siliconflow":
        return siliconflow_reranker(settings)
    if settings.upgrad_reranker == "none":
        return None
    chat = get_provider(settings, "upgrad")
    return RerankConfig(
        name="upgrad-rerank",
        base_url=chat.base_url,
        api_key=chat.api_key,
        ca_cert=chat.ca_cert,
        max_concurrency=chat.max_concurrency,
        requests_per_minute=chat.requests_per_minute,
        model=chat.model,
        kind="chat_listwise",
        extra_body=chat.extra_body,
    )


def validate(settings: Settings) -> None:
    """Fail fast at startup: every key and certificate the active provider needs."""
    get_provider(settings)
    get_embedding(settings)
    get_reranker(settings)


def _ssl_context(ca_cert: Path | None) -> ssl.SSLContext:
    # Verification stays on: the course endpoints are trusted through their own CA file only.
    return (
        ssl.create_default_context(cafile=str(ca_cert)) if ca_cert else ssl.create_default_context()
    )


def make_http_client(endpoint: Endpoint, timeout_s: float) -> httpx.Client:
    """An httpx client that verifies TLS against the endpoint's CA and passes every request
    through the endpoint's process-wide gate."""
    transport = GatedTransport(
        httpx.HTTPTransport(verify=_ssl_context(endpoint.ca_cert)),
        shared_gate(endpoint.base_url, endpoint.max_concurrency, endpoint.requests_per_minute),
    )
    return httpx.Client(transport=transport, timeout=timeout_s)


def make_openai_client(endpoint: Endpoint, timeout_s: float) -> OpenAI:
    # max_retries=0: retries follow the Track B policy in copilot.llm.retry, not the SDK's.
    return OpenAI(
        base_url=endpoint.base_url,
        api_key=endpoint.api_key,
        timeout=timeout_s,
        max_retries=0,
        http_client=make_http_client(endpoint, timeout_s),
    )
