from typing import Any, List, Optional
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, Template
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)


class PromptManager:

    _instance: Optional["PromptManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.templates_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["format_list"] = self._format_list_filter

    @lru_cache(maxsize=128)
    def get_template(self, template_path: str) -> Template:
        return self.env.get_template(template_path)

    def render(self, template_path: str, **variables) -> str:
        template = self.get_template(template_path)
        return template.render(**variables)

    def render_as_list(self, template_path: str, **variables) -> List[str]:
        rendered = self.render(template_path, **variables)
        return [line for line in rendered.split("\n") if line.strip()]

    @staticmethod
    def _format_list_filter(items: List[Any], prefix: str = "- ") -> str:
        return "\n".join(f"{prefix}{item}" for item in items)


def get_prompt_manager() -> PromptManager:
    return PromptManager()
