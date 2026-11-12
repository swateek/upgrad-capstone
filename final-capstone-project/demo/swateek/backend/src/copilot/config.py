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

    # --- client-side gates and retry -----------------------------------------------
    requests_per_minute: int = 60
    max_concurrency: int = 2
    retry_delays_s: tuple[float, ...] = (2.0, 4.0, 8.0)
    request_timeout_s: float = 120.0

    # --- domain-independent ingest -------------------------------------------------
    max_corpus_docs: int = Field(default=2000, description="Track B hard cap on indexed documents")

    @property
    def domain_dir(self) -> Path:
        return self.domains_dir / self.domain


@lru_cache
def get_settings() -> Settings:
    return Settings()
