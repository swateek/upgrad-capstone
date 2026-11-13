"""Runtime settings. Every knob comes from the environment (or the project .env file)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/copilot/config.py -> parents[3] is final-capstone-project/demo/swateek
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- domain pack -------------------------------------------------------------
    # Required: the core has no default domain. Set DOMAIN in .env (see env.sample).
    domain: str
    domains_dir: Path = PROJECT_ROOT / "domains"
    data_dir: Path = PROJECT_ROOT / "data"

    # --- chat model ----------------------------------------------------------------
    # "course" (the Track B endpoint) is planned but deliberately not wired yet.
    llm_provider: Literal["siliconflow", "course"] = "siliconflow"
    chat_model: str = "Qwen/Qwen3-8B"
    siliconflow_api_key: SecretStr | None = None
    siliconflow_base_url: str = "https://api.siliconflow.com/v1"

    # Qwen3 thinking mode. SiliconFlow defaults it to ON, so it is sent explicitly.
    enable_thinking: bool = False

    # --- Track B limits, enforced on every provider --------------------------------
    context_window_tokens: int = 8192  # input + output, per call
    max_output_tokens: int = 1024  # hard ceiling for max_tokens
    default_max_tokens: int = 768
    tokenizer_id: str = "Qwen/Qwen3-8B"

    # --- agent harness (Track B caps; definitions in copilot.agent.context) --------
    agent_step_limit: int = 10  # model calls per query, all roles
    agent_tool_limit: int = 10  # tool executions per query
    agent_token_limit: int = 40000  # prompt + completion tokens per query
    agent_max_tokens: int = 700  # max_tokens for each agent model call
    agent_max_revisions: int = 2  # critic-requested revisions per query (decided 13 Nov)

    # --- client-side gates and retry -----------------------------------------------
    requests_per_minute: int = 60
    max_concurrency: int = 2
    retry_delays_s: tuple[float, ...] = (2.0, 4.0, 8.0)
    request_timeout_s: float = 120.0

    # --- retrieval ------------------------------------------------------------------
    # Unset: embedded Qdrant under data/qdrant (dev/eval). Docker sets http://qdrant:6333.
    qdrant_url: str | None = None
    # --- tracing (Langfuse Cloud; disabled unless both keys are set) -------------------
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"  # .env sets the US region
    tracing_enabled: bool = True
    trace_environment: str = "development"

    # --- cache and rate limit ---------------------------------------------------------
    # Unset: in-process fallback (single worker, dev). Docker sets redis://redis:6379/0.
    redis_url: str | None = None
    rate_limit_chat_per_min: int = 10  # agent turns per conversation per minute
    rate_limit_ip_per_min: int = 60  # all API calls per client IP per minute
    retrieval_cache_ttl_s: int = 24 * 3600

    # --- API -------------------------------------------------------------------------
    allowed_origins: list[str] = ["http://localhost:3400"]

    chunker: str = "by_rule"  # which chunk set is served; the Phase 3 experiment picks the winner

    # --- domain-independent ingest -------------------------------------------------
    max_corpus_docs: int = Field(default=2000, description="Track B hard cap on indexed documents")

    @property
    def domain_dir(self) -> Path:
        return self.domains_dir / self.domain


@lru_cache
def get_settings() -> Settings:
    return Settings()
