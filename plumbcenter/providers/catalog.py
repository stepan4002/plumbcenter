"""Built-in AI provider catalog. Pure data, no I/O, no secrets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class ProviderSpec:
    """One provider the hub knows how to configure and test.

    test_kind selects the authenticated probe implemented in tester.py:
    "openai" (GET {base}/models, Bearer), "anthropic" (GET {base}/v1/models),
    "gemini" (GET {base}/models), "ollama" (GET {base}/api/tags, no key).
    """

    id: str
    name: str
    kind: str  # "cloud" | "local"
    base_url: str
    key_env: str
    needs_key: bool
    default_model: str
    docs_url: str
    test_kind: str


PROVIDERS: Tuple[ProviderSpec, ...] = (
    ProviderSpec(
        "openai", "OpenAI", "cloud",
        "https://api.openai.com/v1", "OPENAI_API_KEY", True,
        "gpt-4.1-mini",
        "https://platform.openai.com/docs/api-reference/models/list",
        "openai",
    ),
    ProviderSpec(
        "anthropic", "Anthropic", "cloud",
        "https://api.anthropic.com", "ANTHROPIC_API_KEY", True,
        "claude-sonnet-4-20250514",
        "https://docs.anthropic.com/en/api/models-list",
        "anthropic",
    ),
    ProviderSpec(
        "gemini", "Google Gemini", "cloud",
        "https://generativelanguage.googleapis.com/v1beta", "GEMINI_API_KEY", True,
        "gemini-2.5-flash",
        "https://ai.google.dev/api/models",
        "gemini",
    ),
    ProviderSpec(
        "openrouter", "OpenRouter", "cloud",
        "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", True,
        "openai/gpt-4.1-mini",
        "https://openrouter.ai/docs/api-reference/models/get-models",
        "openai",
    ),
    ProviderSpec(
        "groq", "Groq", "cloud",
        "https://api.groq.com/openai/v1", "GROQ_API_KEY", True,
        "llama-3.3-70b-versatile",
        "https://console.groq.com/docs/openai",
        "openai",
    ),
    # Auth and base are from https://docs.z.ai/api-reference/introduction (Bearer, paas/v4).
    # That document does not publish a models-list GET. default_model is a documented chat id.
    ProviderSpec(
        "zai", "Z.ai", "cloud",
        "https://api.z.ai/api/paas/v4", "ZAI_API_KEY", True,
        "glm-4.6",
        "https://docs.z.ai/api-reference/introduction",
        "openai",
    ),
    ProviderSpec(
        "ollama", "Ollama", "local",
        "http://127.0.0.1:11434", "", False,
        "llama3.2",
        "https://github.com/ollama/ollama/blob/main/docs/api.md",
        "ollama",
    ),
    # Base is the documented gateway (https://kilo.ai/gateway). GET /models there does not require a key.
    ProviderSpec(
        "kilo", "Kilo", "cloud",
        "https://api.kilo.ai/api/gateway", "KILO_API_KEY", True,
        "kilo-auto/efficient",
        "https://kilo.ai/gateway",
        "openai",
    ),
)


def get_provider(id: str) -> Optional[ProviderSpec]:
    """Return the catalog entry for `id`, or None."""
    if not isinstance(id, str):
        return None
    key = id.strip().lower()
    return next((p for p in PROVIDERS if p.id == key), None)
