"""Provider registry and model cost table."""

from __future__ import annotations

from app.core.config import settings
from app.core.errors import ValidationError
from app.services.ai.base import AIProvider
from app.services.ai.gemini_provider import GeminiProvider
from app.services.ai.openai_provider import (
    GroqProvider,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
)

_PROVIDERS: dict[str, AIProvider] = {
    "gemini": GeminiProvider(),
    "groq": GroqProvider(),
    "openrouter": OpenRouterProvider(),
    "ollama": OllamaProvider(),
    "openai": OpenAIProvider(),
}

PROVIDER_LABELS = {
    "gemini": "Google Gemini (free tier)",
    "groq": "Groq (free tier)",
    "openrouter": "OpenRouter (modelos :free)",
    "ollama": "Ollama (local, sem chave)",
    "openai": "OpenAI (pago)",
}

DEFAULT_MODELS = {
    "gemini": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
    "ollama": "llama3.1",
    "openai": "gpt-4o-mini",
}

PROVIDER_MODELS = {
    "gemini": [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
        "qwen/qwen3-32b",
    ],
    "openrouter": [
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemma-3-27b-it:free",
        "qwen/qwen3-30b-a3b:free",
        "deepseek/deepseek-chat-v3-0324:free",
    ],
    "ollama": ["llama3.1", "llama3.2", "qwen2.5", "mistral", "phi3"],
    "openai": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o", "gpt-4.1"],
}

# USD per 1M tokens (input, output). Zero-cost models fall back to 0.0.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
}


def available_providers() -> list[dict[str, object]]:
    providers = []
    for name, provider in _PROVIDERS.items():
        api_key = get_provider_key(name)
        providers.append(
            {
                "name": name,
                "label": PROVIDER_LABELS.get(name, getattr(provider, "label", name)),
                "configured": bool(api_key) or not getattr(provider, "requires_api_key", True),
                "requires_api_key": bool(getattr(provider, "requires_api_key", True)),
                "default_model": DEFAULT_MODELS.get(name, ""),
                "models": PROVIDER_MODELS.get(name, []),
                "is_default": name == settings.ai_default_provider.lower(),
            }
        )
    return providers


def get_provider(name: str | None) -> AIProvider:
    provider_name = (name or settings.ai_default_provider or "gemini").lower()
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        raise ValidationError(f"Provedor de IA desconhecido: {provider_name}.")
    return provider


def get_provider_key(provider_name: str) -> str:
    mapping = {
        "openai": settings.openai_api_key,
        "gemini": settings.gemini_api_key,
        "groq": settings.groq_api_key,
        "openrouter": settings.openrouter_api_key,
    }
    return mapping.get(provider_name.lower()) or ""


def resolve_api_key(provider_name: str, explicit_key: str | None = None) -> str:
    return explicit_key or get_provider_key(provider_name)


def resolve_model(provider_name: str, model: str | None) -> str:
    provider_name = provider_name.lower()
    if provider_name == settings.ai_default_provider.lower():
        return (model or settings.ai_default_model or DEFAULT_MODELS[provider_name]).strip()
    return (model or DEFAULT_MODELS.get(provider_name, "gemini-2.0-flash")).strip()


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        return 0.0
    prompt_cost = (prompt_tokens / 1_000_000) * pricing[0]
    completion_cost = (completion_tokens / 1_000_000) * pricing[1]
    return round(prompt_cost + completion_cost, 6)
