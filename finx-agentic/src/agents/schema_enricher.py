from __future__ import annotations

import json
import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from agno.models.message import Message
from agno.models.response import ModelResponse

from src.core.llm import create_agno_model_for_agent
from src.core.types import (
    EnrichedColumn,
    EnrichedSchema,
    Relationship,
    TableSchema,
)
from src.prompts.manager import get_prompt_manager

logger = logging.getLogger(__name__)


class SourceType(str, Enum):
    """Identifies the origin and expected content type of a knowledge document."""
    PDF = "pdf_extract"
    CONFLUENCE = "confluence_page"
    URL = "url_content"
    TEXT = "raw_text"
    SCHEMA = "table_schema"


class KnowledgeSource(BaseModel):
    """A single piece of external knowledge attached to an enrichment request.

    Attributes:
        source_type: Origin/format of the document (pdf, confluence, url, text, schema).
        source_name: Human-readable label shown to the LLM (e.g. filename, page title, URL).
        content: Pre-extracted plain text content ready for the LLM.
    """

    source_type: SourceType = SourceType.TEXT
    source_name: str = ""
    content: str

    @classmethod
    def from_text(cls, content: str, name: str = "") -> "KnowledgeSource":
        return cls(source_type=SourceType.TEXT, source_name=name, content=content)

    @classmethod
    def from_pdf(cls, content: str, filename: str = "") -> "KnowledgeSource":
        return cls(source_type=SourceType.PDF, source_name=filename, content=content)

    @classmethod
    def from_confluence(cls, content: str, page_title: str = "", url: str = "") -> "KnowledgeSource":
        name = page_title or url
        return cls(source_type=SourceType.CONFLUENCE, source_name=name, content=content)

    @classmethod
    def from_url(cls, content: str, url: str = "") -> "KnowledgeSource":
        return cls(source_type=SourceType.URL, source_name=url, content=content)

    def render(self) -> str:
        """Return a labelled block ready for prompt injection."""
        header_parts = [f"[{self.source_type.value.upper()}]"]
        if self.source_name:
            header_parts.append(self.source_name)
        return "\n".join([" | ".join(header_parts), self.content])


class LLMColumnDesign(BaseModel):
    name: str = ""
    description: str = ""
    business_terms: List[str] = Field(default_factory=list)
    is_primary_key: bool = False
    column_type: str = ""


class LLMRelationship(BaseModel):
    target_table: str = ""
    relationship_type: str = "join"
    source_column: str = ""
    target_column: str = ""
    description: str = ""


class LLMKGNode(BaseModel):
    id: str = ""
    label: str = ""
    type: str = "table"
    description: str = ""


class LLMKGEdge(BaseModel):
    source: str = ""
    target: str = ""
    label: str = ""
    type: str = "structural"


class LLMKnowledgeGraph(BaseModel):
    nodes: List[LLMKGNode] = Field(default_factory=list)
    edges: List[LLMKGEdge] = Field(default_factory=list)


class TableEnrichmentResponse(BaseModel):
    table_description: str = ""
    ai_description: str = ""
    entity_name: str = ""
    domain: str = ""
    synonyms: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    columns: List[LLMColumnDesign] = Field(default_factory=list)
    relationships: List[LLMRelationship] = Field(default_factory=list)
    knowledge_graph: LLMKnowledgeGraph = Field(
        default_factory=LLMKnowledgeGraph,
    )


class ColumnEnrichmentResponse(BaseModel):
    columns: List[LLMColumnDesign] = Field(default_factory=list)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)
_SINGLE_LINE_COMMENT_RE = re.compile(r'(?<!["\'])//[^\n]*')
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_TOKEN_TRUNCATION_THRESHOLD = 15500


def _repair_truncated_json(text: str) -> Optional[Dict[str, Any]]:
    json_start = text.find("{")
    if json_start < 0:
        return None

    fragment = text[json_start:]

    for trim_pos in [
        fragment.rfind("},") + 1,
        fragment.rfind("],") + 1,
        fragment.rfind("}]") + 2,
        fragment.rfind("}") + 1,
        fragment.rfind("]") + 1,
    ]:
        if trim_pos <= 0:
            continue
        candidate = fragment[:trim_pos]
        candidate = _TRAILING_COMMA_RE.sub(r"\1", candidate)

        open_braces = candidate.count("{") - candidate.count("}")
        open_brackets = candidate.count("[") - candidate.count("]")
        candidate += "]" * max(open_brackets, 0)
        candidate += "}" * max(open_braces, 0)

        try:
            result = json.loads(candidate)
            logger.warning("Recovered partial JSON from truncated LLM output")
            return result
        except json.JSONDecodeError:
            continue

    return None


def _sanitize_llm_json(raw_text: str) -> Dict[str, Any]:
    text = raw_text.strip()

    block_match = _JSON_BLOCK_RE.search(text)
    if block_match:
        text = block_match.group(1).strip()
    elif text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    text = _SINGLE_LINE_COMMENT_RE.sub("", text)
    text = _TRAILING_COMMA_RE.sub(r"\1", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    text = text.replace("'", '"')
    text = re.sub(r"(?<=\{|,)\s*(\w+)\s*:", r' "\1":', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    json_start = text.find("{")
    json_end = text.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        fragment = text[json_start:json_end]
        try:
            return json.loads(fragment)
        except json.JSONDecodeError:
            pass

    repaired = _repair_truncated_json(text)
    if repaired is not None:
        return repaired

    logger.error("Failed to parse LLM JSON output: %s", text[:500])
    raise ValueError(f"LLM returned unparseable JSON: {text[:200]}")


def _parse_structured_response(
    response: ModelResponse,
    response_model: type[BaseModel],
) -> BaseModel:
    if response.parsed is not None and isinstance(response.parsed, response_model):
        return response.parsed

    raw_text = (response.content or "").strip()

    try:
        return response_model.model_validate_json(raw_text)
    except Exception:
        pass

    raw_dict = _sanitize_llm_json(raw_text)
    return response_model.model_validate(raw_dict)


class SchemaEnricher:

    def __init__(self, *, agent_name: str = "schema_enricher"):
        self._model = create_agno_model_for_agent(agent_name)
        self._pm = get_prompt_manager()

    async def enrich_table(
        self,
        schema: TableSchema,
        context_tables: Optional[List[str]] = None,
        context_documents: Optional[List[str]] = None,
        knowledge_sources: Optional[List[KnowledgeSource]] = None,
    ) -> EnrichedSchema:
        """Enrich a table schema using LLM + optional knowledge sources.

        Args:
            schema: The table schema to enrich.
            context_tables: Other table names in the same database (for relationship inference).
            context_documents: Legacy plain-text documents (kept for backward compatibility).
                               Each string is passed as a ``raw_text`` source.
            knowledge_sources: Typed knowledge sources (PDF, Confluence, URL, text, schema).
                               These are merged with ``context_documents`` before rendering.
        """
        system_prompt = self._pm.render("schema_enricher/system.jinja2")
        other_tables = []
        if context_tables:
            other_tables = [t for t in context_tables if t != schema.name][:50]

        # Merge legacy plain strings + typed sources into a single rendered list
        merged_docs: List[str] = []
        for doc in (context_documents or []):
            text = doc.strip()
            if text:
                merged_docs.append(KnowledgeSource.from_text(text).render())
        for src in (knowledge_sources or []):
            text = src.content.strip()
            if text:
                merged_docs.append(src.render())

        user_prompt = self._pm.render(
            "schema_enricher/enrich_table.jinja2",
            table_name=schema.name,
            database=schema.database,
            description=schema.description,
            location=schema.location,
            columns=schema.columns,
            context_tables=other_tables,
            context_documents=merged_docs if merged_docs else None,
        )

        raw = await self._call_llm(
            system_prompt,
            user_prompt,
            response_model=TableEnrichmentResponse,
        )

        enriched = _build_enriched_schema(raw, schema)

        logger.info(
            "Enriched %s: entity=%s, domain=%s, columns=%d, rels=%d, "
            "kg_nodes=%d, kg_edges=%d",
            schema.name,
            enriched.entity_name,
            enriched.domain,
            len(enriched.enriched_columns),
            len(enriched.relationships),
            len(enriched.kg_nodes),
            len(enriched.kg_edges),
        )
        return enriched

    async def enrich_columns(
        self,
        schema: TableSchema,
        column_names: List[str],
        knowledge_sources: Optional[List[KnowledgeSource]] = None,
    ) -> Dict[str, EnrichedColumn]:
        columns = [c for c in schema.columns if c.name in column_names]
        if not columns:
            return {}

        merged_docs: List[str] = []
        for src in (knowledge_sources or []):
            text = src.content.strip()
            if text:
                merged_docs.append(src.render())

        system_prompt = self._pm.render("schema_enricher/system.jinja2")
        user_prompt = self._pm.render(
            "schema_enricher/enrich_columns.jinja2",
            table_name=schema.name,
            database=schema.database,
            all_columns=schema.columns,
            new_columns=columns,
            context_documents=merged_docs if merged_docs else None,
        )

        raw = await self._call_llm(
            system_prompt,
            user_prompt,
            response_model=ColumnEnrichmentResponse,
        )

        result: Dict[str, EnrichedColumn] = {}
        columns_by_name = {c.name: c for c in raw.columns}
        for col in columns:
            design = columns_by_name.get(col.name, LLMColumnDesign())
            result[col.name] = EnrichedColumn(
                name=col.name,
                data_type=col.data_type,
                description=col.description,
                is_partition=col.is_partition,
                is_primary_key=design.is_primary_key or col.is_primary_key,
                sample_values=col.sample_values,
                ai_description=design.description,
                business_terms=design.business_terms,
                column_type=design.column_type,
            )
        return result

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        response_model: type[BaseModel],
    ) -> BaseModel:
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ]

        response: ModelResponse = await self._model.aresponse(
            messages=messages,
            response_format=response_model,
        )

        if response.output_tokens and response.output_tokens >= _TOKEN_TRUNCATION_THRESHOLD:
            logger.warning(
                "LLM output may be truncated: %d output tokens used "
                "(threshold=%d). Consider increasing max_tokens in config.",
                response.output_tokens,
                _TOKEN_TRUNCATION_THRESHOLD,
            )

        return _parse_structured_response(response, response_model)


def _build_enriched_schema(
    llm_result: TableEnrichmentResponse,
    schema: TableSchema,
) -> EnrichedSchema:
    columns_by_name = {c.name: c for c in llm_result.columns}
    enriched_columns: List[EnrichedColumn] = []
    for col in schema.columns:
        design = columns_by_name.get(col.name, LLMColumnDesign())
        enriched_columns.append(
            EnrichedColumn(
                name=col.name,
                data_type=col.data_type,
                description=col.description,
                is_partition=col.is_partition,
                is_primary_key=design.is_primary_key or col.is_primary_key,
                sample_values=col.sample_values,
                ai_description=design.description,
                business_terms=design.business_terms,
                column_type=design.column_type,
            )
        )

    relationships: List[Relationship] = []
    for rel in llm_result.relationships:
        relationships.append(
            Relationship(
                source_table=schema.name,
                target_table=rel.target_table,
                relationship_type=rel.relationship_type,
                source_column=rel.source_column,
                target_column=rel.target_column,
                description=rel.description,
            )
        )

    kg_nodes: List[Dict[str, Any]] = [
        n.model_dump() for n in llm_result.knowledge_graph.nodes
    ]
    kg_edges: List[Dict[str, Any]] = [
        e.model_dump() for e in llm_result.knowledge_graph.edges
    ]

    if not kg_nodes:
        kg_nodes, kg_edges = _build_fallback_kg(
            schema, llm_result, enriched_columns, relationships,
        )

    return EnrichedSchema(
        name=schema.name,
        database=schema.database,
        columns=schema.columns,
        description=llm_result.table_description or schema.description,
        location=schema.location,
        storage_format=schema.storage_format,
        partition_keys=schema.partition_keys,
        row_count=schema.row_count,
        entity_name=(
            llm_result.entity_name
            or schema.name.replace("_", " ").title()
        ),
        domain=llm_result.domain or "business",
        synonyms=llm_result.synonyms,
        tags=llm_result.tags,
        ai_description=llm_result.ai_description,
        enriched_columns=enriched_columns,
        relationships=relationships,
        kg_nodes=kg_nodes,
        kg_edges=kg_edges,
    )


def _build_fallback_kg(
    schema: TableSchema,
    llm_result: TableEnrichmentResponse,
    enriched_columns: List[EnrichedColumn],
    relationships: List[Relationship],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    table_id = f"table:{schema.database}.{schema.name}"
    nodes.append({
        "id": table_id,
        "label": schema.name,
        "type": "table",
        "description": llm_result.table_description or schema.description or "",
    })

    if llm_result.domain:
        domain_id = f"domain:{llm_result.domain}"
        nodes.append({
            "id": domain_id,
            "label": llm_result.domain.replace("_", " ").title(),
            "type": "domain",
            "description": f"Business domain: {llm_result.domain}",
        })
        edges.append({
            "source": table_id,
            "target": domain_id,
            "label": "BELONGS_TO_DOMAIN",
            "type": "structural",
        })

    for col in enriched_columns:
        col_id = f"column:{schema.name}.{col.name}"
        nodes.append({
            "id": col_id,
            "label": col.name,
            "type": "column",
            "description": col.ai_description or col.description or col.data_type,
        })
        edges.append({
            "source": table_id,
            "target": col_id,
            "label": "HAS_COLUMN",
            "type": "structural",
        })

    for rel in relationships:
        target_id = f"table:{rel.target_table}"
        if not any(n["id"] == target_id for n in nodes):
            nodes.append({
                "id": target_id,
                "label": rel.target_table,
                "type": "table",
                "description": "",
            })
        edges.append({
            "source": table_id,
            "target": target_id,
            "label": rel.relationship_type.upper(),
            "type": "business",
        })

    return nodes, edges
