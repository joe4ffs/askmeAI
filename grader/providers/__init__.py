import os

from grader.providers.base import ImageInput, ModelProvider

_PROVIDER_ENV_VAR = "AI_GRADER_PROVIDER"


def get_provider(name: str | None = None) -> ModelProvider:
    """Build a ModelProvider by name.

    Resolution order: explicit `name` arg > AI_GRADER_PROVIDER env var > auto-detect from
    whichever API key is set > "fake" (no key required, runs the full pipeline with canned output).
    """
    name = name or os.environ.get(_PROVIDER_ENV_VAR) or _autodetect()

    if name == "anthropic":
        from grader.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if name == "openai":
        from grader.providers.openai_provider import OpenAIProvider

        return OpenAIProvider()
    if name == "gemini":
        from grader.providers.gemini_provider import GeminiProvider

        return GeminiProvider()
    if name == "ollama":
        from grader.providers.ollama_provider import OllamaProvider

        return OllamaProvider()
    if name == "fake":
        from grader.providers.fake_provider import FakeProvider

        return FakeProvider()

    raise ValueError(
        f"Unknown model provider: {name!r} (expected anthropic, openai, gemini, ollama, or fake)"
    )


def _autodetect() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    return "fake"


__all__ = ["get_provider", "ImageInput", "ModelProvider"]
