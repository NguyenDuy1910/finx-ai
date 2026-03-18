"""Prompt template manager — Jinja2-based prompt rendering with caching."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, List

from jinja2 import Environment, FileSystemLoader, Template

logger = logging.getLogger(__name__)


class PromptManager:
    """Singleton prompt manager with Jinja2 template rendering.

    Templates are loaded from ``src/prompts/templates/`` and cached.
    """

    _instance: PromptManager | None = None

    def __new__(cls) -> PromptManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.templates_dir = Path(__file__).parent
        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["format_list"] = self._format_list_filter

    @lru_cache(maxsize=128)
    def get_template(self, template_path: str) -> Template:
        """Load and cache a Jinja2 template by path."""
        return self.env.get_template(template_path)

    def render(self, template_path: str, **variables: Any) -> str:
        """Render a template with the given variables."""
        template = self.get_template(template_path)
        return template.render(**variables)

    def render_as_list(self, template_path: str, **variables: Any) -> List[str]:
        """Render a template and split into non-empty lines."""
        rendered = self.render(template_path, **variables)
        return [line for line in rendered.split("\n") if line.strip()]

    @staticmethod
    def _format_list_filter(items: List[Any], prefix: str = "- ") -> str:
        """Jinja2 filter: format a list with a prefix per item."""
        return "\n".join(f"{prefix}{item}" for item in items)


def get_prompt_manager() -> PromptManager:
    """Get the singleton PromptManager instance."""
    return PromptManager()
