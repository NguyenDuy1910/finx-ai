from typing import Optional

from config.config_loader import AIModelConfig, get_config


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
        return OpenAIChat(
            id=config.model_id,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

    if provider == "anthropic":
        from agno.models.anthropic import Claude
        return Claude(
            id=config.model_id,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

    raise ValueError(f"Unsupported AI provider: {provider}")

