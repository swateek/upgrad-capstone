"""The two upgrad course endpoints, and HTTP clients that respect their limits.

    chat        Qwen3-8B at UPGRAD_CHAT_BASE_URL (group 031-045), CA vm05-ca.crt.
                1 active request per key for the whole group, 60 requests/min,
                8,192 tokens in + out, max_tokens 1..1024.
    embeddings  bge-small-en-v1.5 at UPGRAD_EMBED_BASE_URL, CA vm02-ca.crt.
                384 dimensions, at most 16 texts per request, each under 512 tokens.

TLS verification is always on, against each endpoint's own CA file. Every request passes one
process-wide gate per endpoint (customs.llm.retry), so the agent, the listwise reranker and the
eval runners never overlap on the course key.

Nothing here makes a request: building a client is offline. Calls happen only when a caller
uses the client, and every such step needs the user's explicit OK (AGENTS.md).
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI

from customs.config import Settings
from customs.llm.retry import GatedTransport, shared_gate

UPGRAD_HOST = "103.42.50.41"
BGE_TOKENIZER = "BAAI/bge-small-en-v1.5"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
BGE_DIMENSIONS = 384

CHAT_CONCURRENCY = 1  # one active request per group key (Track B guide)
EMBED_CONCURRENCY = 1  # shared by every group; one batch at a time
EMBED_BATCH = 16
EMBED_MAX_TOKENS = 512


class EndpointNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class Endpoint:
    name: str  # for logs and traces, e.g. "upgrad-chat"
    base_url: str
    api_key: str = field(repr=False)
    ca_cert: Path
    max_concurrency: int
    requests_per_minute: int
    model: str = ""


@dataclass(frozen=True)
class ChatEndpoint(Endpoint):
    extra_body: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingEndpoint(Endpoint):
    batch_size: int = EMBED_BATCH
    max_tokens: int = EMBED_MAX_TOKENS  # per text; longer texts are embedded in windows
    tokenizer_id: str = BGE_TOKENIZER
    dimensions: int = BGE_DIMENSIONS


def _key(value: Any, var: str) -> str:
    if value is None or not value.get_secret_value().strip():
        raise EndpointNotConfigured(f"{var} is not set. Add it to .env (see env.sample).")
    return value.get_secret_value().strip()


def _cert(settings: Settings, path: Path, var: str) -> Path:
    p = settings.resolve(path)
    if not p.is_file():
        raise EndpointNotConfigured(f"{var} points to {p}, which does not exist.")
    return p


def chat_endpoint(settings: Settings) -> ChatEndpoint:
    return ChatEndpoint(
        name="upgrad-chat",
        base_url=settings.upgrad_chat_base_url,
        api_key=_key(settings.upgrad_chat_api_key, "UPGRAD_CHAT_API_KEY"),
        ca_cert=_cert(settings, settings.upgrad_chat_ca_cert, "UPGRAD_CHAT_CA_CERT"),
        max_concurrency=CHAT_CONCURRENCY,
        requests_per_minute=settings.requests_per_minute,
        model=settings.chat_model,
        # vLLM-style switch for Qwen3's thinking mode (verified by the endpoint check, 17 Nov)
        extra_body={"chat_template_kwargs": {"enable_thinking": settings.enable_thinking}},
    )


def embedding_endpoint(settings: Settings) -> EmbeddingEndpoint:
    return EmbeddingEndpoint(
        name="upgrad-embed",
        base_url=settings.upgrad_embed_base_url,
        api_key=_key(settings.upgrad_embed_api_key, "UPGRAD_EMBED_API_KEY"),
        ca_cert=_cert(settings, settings.upgrad_embed_ca_cert, "UPGRAD_EMBED_CA_CERT"),
        max_concurrency=EMBED_CONCURRENCY,
        requests_per_minute=settings.requests_per_minute,
        model=settings.embedding_model,
    )


def validate(settings: Settings) -> None:
    """Fail fast: every key and certificate is present. Offline; sends nothing."""
    chat_endpoint(settings)
    embedding_endpoint(settings)


def _ssl_context(ca_cert: Path) -> ssl.SSLContext:
    return ssl.create_default_context(cafile=str(ca_cert))


def make_http_client(endpoint: Endpoint, timeout_s: float) -> httpx.Client:
    """An httpx client that verifies TLS against the endpoint's CA and passes every request
    through the endpoint's process-wide gate."""
    transport = GatedTransport(
        httpx.HTTPTransport(verify=_ssl_context(endpoint.ca_cert)),
        shared_gate(endpoint.base_url, endpoint.max_concurrency, endpoint.requests_per_minute),
    )
    return httpx.Client(transport=transport, timeout=timeout_s)


def make_openai_client(endpoint: Endpoint, timeout_s: float) -> OpenAI:
    # max_retries=0: retries follow the Track B policy in customs.llm.retry, not the SDK's.
    return OpenAI(
        base_url=endpoint.base_url,
        api_key=endpoint.api_key,
        timeout=timeout_s,
        max_retries=0,
        http_client=make_http_client(endpoint, timeout_s),
    )
