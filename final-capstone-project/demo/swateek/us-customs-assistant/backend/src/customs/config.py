"""Runtime settings. Every knob comes from the environment (or this app's .env file).

upgrad only: chat on the course chat endpoint, embeddings on the course embedding endpoint.
There is no provider switch and no other model provider in this app.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/customs/config.py -> parents[3] is final-capstone-project/demo/swateek/us-customs-assistant
PROJECT_ROOT = Path(__file__).resolve().parents[3]

AgentMode = Literal["planner", "router", "tool_calling", "single_rag"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- paths -------------------------------------------------------------------------
    pack_dir: Path = PROJECT_ROOT / "pack"  # rules, corpus manifest, prompts, eval sets
    data_dir: Path = PROJECT_ROOT / "data"  # gitignored: raw downloads, chunks, local Qdrant

    # --- upgrad course endpoints (group 031-045). Cert paths may be relative to PROJECT_ROOT.
    chat_model: str = "Qwen/Qwen3-8B"
    upgrad_chat_base_url: str = "https://103.42.50.41:1033/v1"
    upgrad_chat_api_key: SecretStr | None = None
    upgrad_chat_ca_cert: Path = Path("certs/vm05-ca.crt")
    upgrad_embed_base_url: str = "https://103.42.50.41:1035/v1"
    upgrad_embed_api_key: SecretStr | None = None
    upgrad_embed_ca_cert: Path = Path("certs/vm02-ca.crt")
    embedding_model: str = "bge-small-en-v1.5"

    # Reranker (plan D6, decided in the retrieval experiment): none by default. listwise =
    # Qwen3-8B on the course chat endpoint (+1 call per search); cross_encoder = local
    # ms-marco-MiniLM (needs `uv sync --group experiment`).
    reranker: Literal["none", "listwise", "cross_encoder"] = "none"

    # Qwen3 thinking mode; off on every default path.
    enable_thinking: bool = False

    # --- Track B limits, enforced on every call --------------------------------------
    context_window_tokens: int = 8192  # input + output, per call
    max_output_tokens: int = 1024  # the endpoint refuses max_tokens > 1024
    default_max_tokens: int = 768
    tokenizer_id: str = "Qwen/Qwen3-8B"
    json_retries: int = 2  # malformed JSON: retries with the error fed back, then escalate

    # --- agent (plan §4) -----------------------------------------------------------------
    agent_mode: AgentMode = "planner"
    agent_step_limit: int = 10  # model calls per question (listwise rerank calls count)
    agent_tool_limit: int = 10  # tool calls per question
    agent_token_limit: int = 12000  # prompt + completion tokens per question (mentor 2.5)
    advisory_review: bool = True  # the verifier's model review (recorded, never blocks)

    # --- client-side gate and retry (Track B guide) -----------------------------------------
    requests_per_minute: int = 60  # per key
    retry_delays_s: tuple[float, ...] = (2.0, 4.0, 8.0)
    request_timeout_s: float = 120.0

    # --- retrieval ------------------------------------------------------------------------
    # Unset: embedded Qdrant under data/qdrant (dev/eval). Docker sets http://qdrant:6333.
    qdrant_url: str | None = None
    # Retrieval defaults chosen by the experiment (docs/results/retrieval-decisions.md).
    chunker: Literal["paragraph", "section", "window200"] = "window200"
    use_query_prefix: bool = True  # bge query instruction
    topic_filter: bool = True  # search_regulations keeps sources matching the rule's topics
    passage_budget_tokens: int = 1500  # passages per search, filled best first
    max_corpus_docs: int = Field(default=2000, description="Track B hard cap on documents")

    # --- tracing (separate Langfuse project; off unless both keys are set) ------------
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"
    tracing_enabled: bool = True
    trace_environment: str = "development"

    # --- cache, rate limit, sessions ------------------------------------------------------
    # Unset: in-process fallback (single worker). Docker sets redis://redis:6379/0.
    redis_url: str | None = None
    rate_limit_chat_per_min: int = 10  # questions per conversation per minute
    rate_limit_ip_per_min: int = 60  # all API calls per client per minute
    retrieval_cache_ttl_s: int = 24 * 3600
    answer_cache_enabled: bool = True  # off for official eval runs
    session_ttl_s: int = 6 * 3600  # conversation state is purged after this (plan §7)

    # --- API ------------------------------------------------------------------------------
    allowed_origins: list[str] = ["http://localhost:3500"]

    @property
    def results_dir(self) -> Path:
        return PROJECT_ROOT / "docs" / "results"

    def resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else PROJECT_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
