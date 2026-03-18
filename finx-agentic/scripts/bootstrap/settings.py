from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


def _default_base_url() -> str:
    return os.getenv("LLM_BASE_URL", os.getenv("NINE_ROUTER_BASE_URL", "https://api.openai.com/v1"))


def _default_api_key() -> str:
    return os.getenv("LLM_API_KEY", os.getenv("NINE_ROUTER_API_KEY", os.getenv("OPENAI_API_KEY", "")))


def _default_model() -> str:
    return os.getenv("LLM_MODEL", os.getenv("NINE_ROUTER_MODEL", "gpt-4.1-mini"))


class BootstrapSettings(BaseSettings):
    finx_data_output_dir: Path = Field(
        default=Path(__file__).parents[3] / "finx-data" / "output",
    )
    bootstrap_state_path: Path = Field(
        default=Path(__file__).parent / ".bootstrap_state.json",
    )
    bootstrap_errors_path: Path = Field(
        default=Path(__file__).parent / "bootstrap_errors.jsonl",
    )

    falkordb_host: str = Field(default="localhost")
    falkordb_port: int = Field(default=6379)
    falkordb_graph: str = Field(default="finx_knowledge")

    llm_base_url: str = Field(default_factory=_default_base_url)
    llm_api_key: str = Field(default_factory=_default_api_key)
    llm_model: str = Field(default_factory=_default_model)
    llm_max_tokens: int = Field(default=8000)

    batch_size: int = Field(default=20)
    dry_run: bool = Field(default=False)
    filter_domain: str | None = Field(default=None)
    one_file: str | None = Field(default=None)
    resume: bool = Field(default=True)
    max_top_columns: int = Field(default=5)
    schema_subdir: str = Field(default="schema")
    ingest_unstructured_confluence: bool = Field(default=True)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "populate_by_name": True,
    }


def get_settings() -> BootstrapSettings:
    return BootstrapSettings()
