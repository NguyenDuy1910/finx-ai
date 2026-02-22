from typing import Optional

from config.config_loader import AIModelConfig, get_config

_NO_TEMPERATURE_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _supports_temperature(model_id: str) -> bool:
    """Check if a model supports custom temperature values."""
    return not model_id.startswith(_NO_TEMPERATURE_PREFIXES)


def create_model(config: Optional[AIModelConfig] = None):
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
        # Some models (GPT-5, o-series) don't support custom temperature
        kwargs: dict = {
            "id": config.model_id,
            "max_completion_tokens": config.max_tokens,
        }
        if _supports_temperature(config.model_id):
            kwargs["temperature"] = config.temperature
        return OpenAIChat(**kwargs)

    if provider == "anthropic":
        from agno.models.anthropic import Claude
        return Claude(
            id=config.model_id,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

    raise ValueError(f"Unsupported AI provider: {provider}")


def create_model_for_agent(agent_name: str):
    """
    Create a model using the per-agent config from team_workflow in config.json.
    Falls back to the global ai_model config if no agent-specific config exists.

    Usage:
        model = create_model_for_agent("knowledge_agent")
    """
    app_config = get_config()
    agent_config = app_config.get_agent_model_config(agent_name)
    if agent_config is not None:
        return create_model(agent_config)
    return create_model()

