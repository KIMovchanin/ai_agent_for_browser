from .anthropic_provider import AnthropicProvider
from .base import BaseLLM
from .gemini_provider import GeminiProvider
from .mock_provider import MockProvider
from .openai_provider import OpenAIProvider


def create_llm(settings) -> BaseLLM:
    provider = settings.llm_provider
    if provider == "mock":
        return MockProvider()
    if settings.dry_run:
        return MockProvider()
    if provider == "ollama":
        api_key = settings.ollama_api_key or "local"
        return OpenAIProvider(
            api_key=api_key,
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_s=settings.request_timeout_s,
        )
    if provider in {"gemini", "google"}:
        if not settings.google_api_key:
            return MockProvider("Dry-run: missing Google API key.")
        provider_instance = GeminiProvider(
            api_key=settings.google_api_key,
            model=settings.gemini_model,
            timeout_s=settings.request_timeout_s,
            base_url=settings.gemini_base_url,
        )
        provider_instance.validate_model()
        return provider_instance
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            return MockProvider("Dry-run: missing Anthropic API key.")
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            timeout_s=settings.request_timeout_s,
        )
    if not settings.openai_api_key:
        return MockProvider("Dry-run: missing OpenAI-compatible API key.")
    return OpenAIProvider(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        timeout_s=settings.request_timeout_s,
    )
