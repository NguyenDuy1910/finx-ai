"""Unified LLM adapter layer.

Provides a single entry-point for creating LLM clients used by both the
graph knowledge pipeline (raw completions) and the agno agent framework.

Usage — raw adapter (graph pipeline, direct calls)::

    from src.core.llm import create_llm_adapter
    adapter = create_llm_adapter("openai", api_key="...", model="gpt-4.1-mini")
    text = adapter.complete(system="...", user="...")

Usage — agno model (for Agent / Team)::

    from src.core.llm import create_agno_model, create_agno_model_for_agent
    model = create_agno_model()                           # global default
    model = create_agno_model_for_agent("sql_generator_agent")  # per-agent
"""

from src.core.llm.protocol import LLMAdapter
from src.core.llm.factory import (
    create_agno_model,
    create_agno_model_for_agent,
    create_llm_adapter,
)

__all__ = [
    "LLMAdapter",
    "create_agno_model",
    "create_agno_model_for_agent",
    "create_llm_adapter",
]
