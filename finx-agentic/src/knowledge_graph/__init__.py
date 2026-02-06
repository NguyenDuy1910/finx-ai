"""
Knowledge Graph Module for Text2SQL Semantic Search

This module provides a graph-based knowledge system for translating
natural language queries to SQL using FalkorDB as the graph database.

Components:
- FalkorDBClient: Connection wrapper for FalkorDB
- GraphSchemaManager: Schema initialization and management
- SemanticSearchService: Entity resolution and pattern matching
- Text2SQLPipeline: Complete NL to SQL translation pipeline
- SchemaLoader: Load schemas from Athena, JSON, or dictionaries
"""

from .falkordb_client import FalkorDBClient, get_falkordb_client
from .schema_manager import GraphSchemaManager
from .semantic_search import SemanticSearchService
from .text2sql_pipeline import Text2SQLPipeline
from .schema_loader import SchemaLoader

__all__ = [
    "FalkorDBClient",
    "get_falkordb_client",
    "GraphSchemaManager",
    "SemanticSearchService",
    "Text2SQLPipeline",
    "SchemaLoader",
]

