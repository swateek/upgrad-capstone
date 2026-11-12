"""Provider factory. One place decides base URL, key, model id and provider-specific body fields."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from copilot.config import Settings


class ProviderNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key: str = field(repr=False)
    model: str
    max_concurrency: int
    requests_per_minute: int
    extra_body: dict[str, Any] = field(default_factory=dict)


def get_provider(settings: Settings) -> ProviderConfig:
    if settings.llm_provider == "siliconflow":
        if settings.siliconflow_api_key is None:
            raise ProviderNotConfigured(
                "SILICONFLOW_API_KEY is not set. Copy env.sample to .env and fill it in."
            )
        return ProviderConfig(
            name="siliconflow",
            base_url=settings.siliconflow_base_url,
            api_key=settings.siliconflow_api_key.get_secret_value(),
            model=settings.chat_model,
            max_concurrency=settings.max_concurrency,
            requests_per_minute=settings.requests_per_minute,
            extra_body={"enable_thinking": settings.enable_thinking},
        )
    if settings.llm_provider == "course":
        # Planned: the Track B course endpoint replaces SiliconFlow for inference later.
        # Not wired on purpose; see docs/implementation-plan.md section 6.2.
        raise ProviderNotConfigured("The course endpoint is not enabled yet.")
    raise ProviderNotConfigured(f"Unknown provider: {settings.llm_provider}")


def make_openai_client(provider: ProviderConfig, timeout_s: float) -> OpenAI:
    # max_retries=0: retries follow the Track B policy in copilot.llm.retry, not the SDK's.
    return OpenAI(
        base_url=provider.base_url,
        api_key=provider.api_key,
        timeout=timeout_s,
        max_retries=0,
    )
