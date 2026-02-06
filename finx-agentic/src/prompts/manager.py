"""
Prompt Template Manager

Handles loading, caching, and rendering of Jinja2 prompt templates.
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, Template
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)


class PromptManager:
    """Manages prompt templates with Jinja2 rendering."""
    
    _instance: Optional['PromptManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.templates_dir = Path(__file__).parent / 'templates'
        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True
        )
        
        # Custom filters
        self.env.filters['format_list'] = self._format_list_filter
        
        logger.info(f"PromptManager initialized with templates from: {self.templates_dir}")
    
    @lru_cache(maxsize=128)
    def get_template(self, template_path: str) -> Template:
        """
        Load and cache a template.
        
        Args:
            template_path: Path relative to templates/ directory
            
        Returns:
            Jinja2 Template object
        """
        try:
            return self.env.get_template(template_path)
        except Exception as e:
            logger.error(f"Failed to load template '{template_path}': {e}")
            raise
    
    def render(self, template_path: str, **variables) -> str:
        """
        Render a template with variables.
        
        Args:
            template_path: Path relative to templates/ directory
            **variables: Template variables
            
        Returns:
            Rendered template string
        """
        template = self.get_template(template_path)
        return template.render(**variables)
    
    def render_as_list(self, template_path: str, **variables) -> List[str]:
        """
        Render template and split into list of lines.
        Useful for agent instructions format.
        
        Args:
            template_path: Path relative to templates/ directory
            **variables: Template variables
            
        Returns:
            List of non-empty lines
        """
        rendered = self.render(template_path, **variables)
        return [line for line in rendered.split('\n') if line.strip()]
    
    @staticmethod
    def _format_list_filter(items: List[Any], prefix: str = '- ') -> str:
        """Jinja2 filter to format list items."""
        return '\n'.join(f"{prefix}{item}" for item in items)


def get_prompt_manager() -> PromptManager:
    """Get singleton PromptManager instance."""
    return PromptManager()
