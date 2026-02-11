from typing import Any, Dict, Optional

from agno.agent import Agent

from src.core.model_factory import create_model
from src.core.types import ValidationResult, SchemaContext
from src.prompts.manager import get_prompt_manager


def create_validation_agent(
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
) -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("validation/instructions.jinja2")

    return Agent(
        name="Validation",
        model=create_model(),
        description="Validates generated SQL queries for correctness and safety",
        instructions=[instructions],
        output_schema=ValidationResult,
        markdown=False,
        session_id=session_id,
        session_state=session_state or {},
    )


def build_validate_prompt(
    generated_sql: str,
    database: str,
    schema_context: Optional[SchemaContext] = None,
    original_query: Optional[str] = None,
) -> str:
    pm = get_prompt_manager()
    return pm.render(
        "validation/validate.jinja2",
        generated_sql=generated_sql,
        database=database,
        schema_context=schema_context,
        original_query=original_query,
    )

