import os
import json
from typing import Dict, List, Any
from openai import OpenAI


class DomainGenerator:
    
    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        )
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o")
    
    def generate_domain_terms(self, table_schema: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self._build_prompt(table_schema)
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a data analyst expert. Generate domain terms and entity mappings for database tables. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return self._merge_with_schema(table_schema, result)
    
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
    
    def _merge_with_schema(
        self,
        schema: Dict[str, Any],
        generated: Dict[str, Any]
    ) -> Dict[str, Any]:
        result = {
            "name": schema["name"],
            "database": schema.get("database", ""),
            "description": generated.get("description", schema.get("description", "")),
            "columns": [],
            "entity": {
                "name": generated.get("entity", schema["name"].title()),
                "domain": generated.get("domain", "business"),
                "synonyms": generated.get("synonyms", [])
            }
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
                "foreign_key": col_name.endswith("_id") and col_name != f"{schema['name']}_id"
            })
        
        return result

