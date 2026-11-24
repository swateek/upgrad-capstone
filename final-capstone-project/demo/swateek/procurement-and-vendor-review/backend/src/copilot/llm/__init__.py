"""Chat-model provider layer: provider factory, token budget, retry, rate/concurrency gate."""

from copilot.llm.budget import TokenBudgetExceeded, check_budget, validate_max_tokens
from copilot.llm.providers import ProviderConfig, get_provider, make_openai_client
from copilot.llm.retry import RateGate, call_with_retry

__all__ = [
    "ProviderConfig",
    "RateGate",
    "TokenBudgetExceeded",
    "call_with_retry",
    "check_budget",
    "get_provider",
    "make_openai_client",
    "validate_max_tokens",
]
