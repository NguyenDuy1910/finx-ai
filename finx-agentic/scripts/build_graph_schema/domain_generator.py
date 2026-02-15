import os
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI

from src.core.cost_tracker import estimate_cost

logger = logging.getLogger(__name__)


@dataclass
class LLMUsage:
    step: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    duration_s: float = 0.0
    cost_usd: float = 0.0


@dataclass
class LLMCostTracker:
    calls: List[LLMUsage] = field(default_factory=list)

    def add(self, usage: LLMUsage) -> None:
        self.calls.append(usage)

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    @property
    def total_tokens(self) -> int:
        return sum(c.total_tokens for c in self.calls)

    @property
    def total_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    @property
    def total_duration_s(self) -> float:
        return sum(c.duration_s for c in self.calls)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "calls": [
                {
                    "step": c.step,
                    "model": c.model,
                    "input_tokens": c.input_tokens,
                    "output_tokens": c.output_tokens,
                    "total_tokens": c.total_tokens,
                    "duration_s": round(c.duration_s, 3),
                    "cost_usd": round(c.cost_usd, 6),
                }
                for c in self.calls
            ],
            "totals": {
                "llm_calls": len(self.calls),
                "input_tokens": self.total_input_tokens,
                "output_tokens": self.total_output_tokens,
                "total_tokens": self.total_tokens,
                "total_cost_usd": round(self.total_cost_usd, 6),
                "total_duration_s": round(self.total_duration_s, 3),
            },
        }

    def print_summary(self) -> None:
        print("\n" + "=" * 90)
        print("LLM COST SUMMARY (Schema Sync)")
        print("=" * 90)
        print(
            f"{'Step':<35} {'Model':<18} {'In Tok':>8} {'Out Tok':>8} "
            f"{'Duration':>9} {'Cost ($)':>10}"
        )
        print("-" * 90)
        for c in self.calls:
            print(
                f"{c.step:<35} {c.model:<18} {c.input_tokens:>8,} {c.output_tokens:>8,} "
                f"{c.duration_s:>8.2f}s ${c.cost_usd:>9.6f}"
            )
        print("-" * 90)
        print(
            f"{'TOTAL':<35} {'':<18} {self.total_input_tokens:>8,} {self.total_output_tokens:>8,} "
            f"{self.total_duration_s:>8.2f}s ${self.total_cost_usd:>9.6f}"
        )
        print(f"{'LLM calls':<35} {len(self.calls)}")
        print("=" * 90 + "\n")


class DomainGenerator:

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        )
        self.model = os.getenv("AI_MODEL_ID")
        self.cost_tracker = LLMCostTracker()

    async def generate_domain_terms(self, table_schema: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self._build_prompt(table_schema)
        result = await self._call_llm(
            "You are a data analyst expert. Generate domain terms and entity mappings for database tables. Return only valid JSON.",
            prompt,
            step=f"generate_domain:{table_schema['name']}",
        )
        return self._merge_with_schema(table_schema, result)

    async def generate_column_terms(
        self,
        table_schema: Dict[str, Any],
        column_names: List[str],
        existing_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        columns = [c for c in table_schema["columns"] if c["name"] in column_names]
        if not columns:
            return {}

        prompt = self._build_column_prompt(table_schema, columns)
        result = await self._call_llm(
            "You are a data analyst expert. Generate domain terms for specific database columns. Return only valid JSON.",
            prompt,
            step=f"generate_columns:{table_schema['name']}:{','.join(column_names)}",
        )

        if existing_schema is None:
            return result

        return self._merge_column_update(existing_schema, table_schema, result, column_names)

    async def _call_llm(self, system_prompt: str, user_prompt: str, step: str = "") -> Dict[str, Any]:
        logger.info(f"[LLM] model={self.model} step={step}")
        start = time.monotonic()
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        duration = time.monotonic() - start

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0
        cost = estimate_cost(self.model, input_tokens, output_tokens) or 0.0

        self.cost_tracker.add(LLMUsage(
            step=step,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            duration_s=duration,
            cost_usd=cost,
        ))

        return json.loads(response.choices[0].message.content)

    def _build_prompt(self, schema: Dict[str, Any]) -> str:
        columns_info = "\n".join([
            f"- {col['name']} ({col['type']}): {col.get('description', '')}"
            for col in schema["columns"]
        ])

        return f"""Analyze this database table and generate domain terms:

Table: {schema['name']}
Description: {schema.get('description', 'No description')}
Database: {schema.get('database', '')}

Columns:
{columns_info}

Generate JSON with:
1. entity: business entity name (e.g., "Customer", "Order", "Transaction")
2. domain: business domain (e.g., "sales", "finance", "inventory", "customer")
3. synonyms: list of alternative names for this entity
4. column_terms: for each column, provide terms/synonyms users might use

Return format:
{{
    "entity": "EntityName",
    "domain": "domain_name",
    "synonyms": ["alt1", "alt2"],
    "description": "business description of this table",
    "column_terms": {{
        "column_name": {{
            "terms": ["term1", "term2"],
            "description": "what this column represents"
        }}
    }}
}}"""

    def _build_column_prompt(
        self,
        schema: Dict[str, Any],
        columns: List[Dict[str, Any]],
    ) -> str:
        columns_info = "\n".join([
            f"- {col['name']} ({col['type']}): {col.get('description', '')}"
            for col in columns
        ])

        all_columns_info = "\n".join([
            f"- {col['name']} ({col['type']})"
            for col in schema["columns"]
        ])

        return f"""Generate domain terms for NEW columns added to an existing table.

Table: {schema['name']}
Database: {schema.get('database', '')}

All columns in table (for context):
{all_columns_info}

NEW columns to generate terms for:
{columns_info}

Return JSON with column_terms only for the new columns:
{{
    "column_terms": {{
        "column_name": {{
            "terms": ["term1", "term2"],
            "description": "what this column represents"
        }}
    }}
}}"""

    def _merge_with_schema(
        self,
        schema: Dict[str, Any],
        generated: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = {
            "name": schema["name"],
            "database": schema.get("database", ""),
            "description": generated.get("description", schema.get("description", "")),
            "columns": [],
            "entity": {
                "name": generated.get("entity", schema["name"].title()),
                "domain": generated.get("domain", "business"),
                "synonyms": generated.get("synonyms", []),
            },
        }

        column_terms = generated.get("column_terms", {})

        for col in schema["columns"]:
            col_name = col["name"]
            col_info = column_terms.get(col_name, {})
            result["columns"].append({
                "name": col_name,
                "type": col["type"],
                "description": col_info.get("description", col.get("description", "")),
                "terms": col_info.get("terms", []),
                "primary_key": col_name.endswith("_id") and col_name == f"{schema['name']}_id",
                "foreign_key": col_name.endswith("_id") and col_name != f"{schema['name']}_id",
            })

        return result

    def _merge_column_update(
        self,
        existing_schema: Dict[str, Any],
        current_schema: Dict[str, Any],
        generated: Dict[str, Any],
        new_column_names: List[str],
    ) -> Dict[str, Any]:
        result = {
            "name": existing_schema["name"],
            "database": existing_schema.get("database", ""),
            "description": existing_schema.get("description", ""),
            "entity": existing_schema.get("entity", {}),
            "columns": [],
        }

        existing_col_map = {c["name"]: c for c in existing_schema.get("columns", [])}
        current_col_map = {c["name"]: c for c in current_schema.get("columns", [])}
        column_terms = generated.get("column_terms", {})

        for col in current_schema["columns"]:
            col_name = col["name"]
            if col_name in new_column_names:
                col_info = column_terms.get(col_name, {})
                result["columns"].append({
                    "name": col_name,
                    "type": col["type"],
                    "description": col_info.get("description", col.get("description", "")),
                    "terms": col_info.get("terms", []),
                    "primary_key": col_name.endswith("_id") and col_name == f"{current_schema['name']}_id",
                    "foreign_key": col_name.endswith("_id") and col_name != f"{current_schema['name']}_id",
                })
            elif col_name in existing_col_map:
                result["columns"].append(existing_col_map[col_name])
            else:
                result["columns"].append({
                    "name": col_name,
                    "type": col["type"],
                    "description": col.get("description", ""),
                    "terms": [],
                    "primary_key": False,
                    "foreign_key": False,
                })

        return result

