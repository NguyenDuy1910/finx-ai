"""Schema enricher — AI-powered table metadata enrichment.

Provides:
* ``SourceType`` — enum of document source types.
* ``KnowledgeSource`` — typed document container for enrichment context.
* ``SchemaEnricher`` — orchestrator that calls the LLM to produce column
  descriptions, business terms, and relationship suggestions for a DB table.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source typing
# ---------------------------------------------------------------------------

class SourceType(str, enum.Enum):
    """Kind of knowledge document fed into the enricher."""

    TEXT = "text"
    PDF = "pdf"
    PDF_EXTRACT = "pdf_extract"
    CONFLUENCE_PAGE = "confluence_page"
    URL_CONTENT = "url_content"
    RAW_TEXT = "raw_text"
    TABLE_SCHEMA = "table_schema"


@dataclass
class KnowledgeSource:
    """A single document supplied as enrichment context."""

    source_type: SourceType
    source_name: str = ""
    content: str = ""


# ---------------------------------------------------------------------------
# Enrichment result types
# ---------------------------------------------------------------------------

@dataclass
class EnrichedColumn:
    name: str = ""
    data_type: str = ""
    description: str = ""
    ai_description: str = ""
    business_terms: List[str] = field(default_factory=list)
    is_primary_key: bool = False
    column_type: Optional[str] = None


@dataclass
class EnrichedRelationship:
    source_table: str = ""
    source_column: str = ""
    target_table: str = ""
    target_column: str = ""
    relationship_type: str = ""


@dataclass
class EnrichmentResult:
    enriched_columns: List[EnrichedColumn] = field(default_factory=list)
    relationships: List[EnrichedRelationship] = field(default_factory=list)
    table_description: str = ""


# ---------------------------------------------------------------------------
# SchemaEnricher
# ---------------------------------------------------------------------------

class SchemaEnricher:
    """Enriches a database table schema with AI-generated metadata.

    This is a placeholder implementation. The full version calls an LLM
    with the table DDL + context documents to produce column descriptions,
    business term mappings, and relationship suggestions.
    """

    async def enrich_table(
        self,
        schema: Any,
        *,
        context_tables: Optional[List[Any]] = None,
        context_documents: Optional[List[str]] = None,
        knowledge_sources: Optional[List[KnowledgeSource]] = None,
    ) -> EnrichmentResult:
        """Enrich a single table schema (placeholder — returns empty result)."""
        logger.warning(
            "SchemaEnricher.enrich_table called but not yet implemented; "
            "returning empty result for table=%s",
            getattr(schema, "name", "?"),
        )
        return EnrichmentResult()
