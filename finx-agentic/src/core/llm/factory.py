from __future__ import annotations

from typing import Optional

from config.config_loader import AIModelConfig, get_config

from .protocol import LLMAdapter

# ── OpenAI reasoning models that do not accept a temperature param ────────
_NO_TEMPERATURE_PREFIXES = ("o1", "o3", "o4")


def _supports_temperature(model_id: str) -> bool:
    """Check if model supports temperature. Handles prefixed IDs like 'cx/o4-mini'."""
    # Strip any provider prefix (e.g. "cx/o4-mini" → "o4-mini")
    bare = model_id.rsplit("/", 1)[-1] if "/" in model_id else model_id
    return not bare.startswith(_NO_TEMPERATURE_PREFIXES)


def create_llm_adapter(
    provider: str,
    api_key: str,
    model: str,
    *,
    base_url: str | None = None,
) -> LLMAdapter:
    """Create a lightweight LLM adapter for raw completions.

    Supports: openai | 9router | vllm | anthropic | google | gemini
    """
    p = provider.lower()

    if p in ("openai", "9router", "vllm"):
        from .openai_adapter import OpenAIAdapter

        return OpenAIAdapter(api_key=api_key, model=model, base_url=base_url)

    if p == "anthropic":
        from .anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(api_key=api_key, model=model)

    if p in ("google", "gemini"):
        from .google_adapter import GoogleAdapter

        return GoogleAdapter(api_key=api_key, model=model)

    raise ValueError(f"Unsupported LLM provider: {provider!r}")


def create_llm_adapter_from_config(
    config: Optional[AIModelConfig] = None,
) -> LLMAdapter:
    """Create a raw LLM adapter using app configuration."""
    if config is None:
        config = get_config().ai_model
    return create_llm_adapter(
        provider=config.provider,
        api_key=config.api_key,
        model=config.model_id,
        base_url=config.base_url,
    )


def create_llm_adapter_for_agent(agent_name: str) -> LLMAdapter:
    """Create a raw LLM adapter for a specific agent (falls back to global)."""
    app_config = get_config()
    agent_config = app_config.get_agent_model_config(agent_name)
    if agent_config is not None:
        return create_llm_adapter_from_config(agent_config)
    return create_llm_adapter_from_config()


def create_agno_model(config: Optional[AIModelConfig] = None):
    """Create an agno Model instance for use with Agent / Team.

    Reads from the global ``AppConfig`` when *config* is not supplied.
    """
    if config is None:
        config = get_config().ai_model

    provider = config.provider.lower()

    if provider == "google":
        from agno.models.google import Gemini

        return Gemini(
            id=config.model_id,
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
        )

    if provider == "openai":
        from agno.models.openai import OpenAIChat

        kwargs: dict = {
            "id": config.model_id,
            "max_completion_tokens": config.max_tokens,
        }
        if _supports_temperature(config.model_id):
            kwargs["temperature"] = config.temperature
        return OpenAIChat(**kwargs)

    if provider == "9router":
        from agno.models.openai.like import OpenAILike

        kwargs: dict = {
            "id": config.model_id,
            "api_key": config.api_key,
            "base_url": config.base_url,
            "max_completion_tokens": config.max_tokens,
        }
        if _supports_temperature(config.model_id):
            kwargs["temperature"] = config.temperature
        return OpenAILike(**kwargs)

    if provider == "anthropic":
        from agno.models.anthropic import Claude

        return Claude(
            id=config.model_id,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

    raise ValueError(f"Unsupported AI provider: {provider}")


def create_agno_model_for_agent(agent_name: str):
    """Create an agno Model for a named agent (falls back to global config)."""
    app_config = get_config()
    agent_config = app_config.get_agent_model_config(agent_name)
    if agent_config is not None:
        return create_agno_model(agent_config)
    return create_agno_model()
