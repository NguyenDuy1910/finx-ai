"""
Graph-based Text2SQL Tool

Provides an AI assistant tool for translating natural language
to SQL using the FalkorDB graph knowledge base.

Features:
- Semantic entity resolution
- Pattern-based SQL generation
- Historical query learning
- Confidence scoring
- Detailed explanations
"""

import json
import logging
from typing import Any, Dict, List, Optional

from agno.tools import Toolkit
from agno.utils.log import logger as agno_logger

from src.knowledge_graph import (
    FalkorDBClient,
    get_falkordb_client,
    GraphSchemaManager,
    SemanticSearchService,
    Text2SQLPipeline
)
from config import get_config

logger = logging.getLogger(__name__)


class GraphText2SQLTool(Toolkit):
    """
    Text2SQL tool powered by FalkorDB graph knowledge base.
    
    This tool translates natural language questions into SQL queries
    by leveraging a graph database containing:
    - Database schema (tables, columns, relationships)
    - Natural language patterns and SQL templates
    - Historical query examples
    - Domain entities and synonyms
    """
    
    def __init__(
        self,
        database: Optional[str] = None,
        auto_initialize: bool = True
    ):
        """
        Initialize the Graph Text2SQL tool.
        
        Args:
            database: Default database name for queries
            auto_initialize: Whether to auto-initialize the graph schema
        """
        super().__init__(name="graph_text2sql_tool")
        
        self.config = get_config()
        self.database = database or self.config.mcp.athena_database
        
        # Initialize FalkorDB client
        self.client = get_falkordb_client(
            host=self.config.falkordb.host,
            port=self.config.falkordb.port
        )
        
        # Initialize components
        self.schema_manager = GraphSchemaManager(self.client)
        self.search_service = SemanticSearchService(self.client)
        self.pipeline = Text2SQLPipeline(self.client, self.database)
        
        # Register tools
        self.register(self.translate_to_sql)
        self.register(self.search_knowledge_graph)
        self.register(self.add_table_to_knowledge)
        self.register(self.add_query_example)
        self.register(self.initialize_graph)
        
        # Auto-initialize if enabled
        if auto_initialize:
            try:
                self._ensure_initialized()
            except Exception as e:
                logger.warning(f"Auto-initialization failed: {e}")
    
    def _ensure_initialized(self) -> None:
        """Ensure the graph schema is initialized."""
        try:
            self.schema_manager.initialize_schema()
            self.schema_manager.populate_default_patterns()
            logger.info("Graph knowledge base initialized")
        except Exception as e:
            logger.warning(f"Schema initialization warning: {e}")
    
    def translate_to_sql(self, question: str) -> str:
        """
        Translate a natural language question to SQL.
        
        Uses the graph knowledge base to understand the question,
        match patterns, and generate accurate SQL.
        
        Args:
            question: Natural language question about data
            
        Returns:
            JSON string containing the SQL query, explanation, and confidence
            
        Example:
            >>> translate_to_sql("How many customers do we have?")
            Returns SQL: SELECT COUNT(*) FROM customers
        """
        try:
            result = self.pipeline.translate(question)
            
            response = {
                "sql": result.sql,
                "explanation": result.explanation,
                "confidence": result.confidence.value,
                "graph_path": result.graph_path,
                "assumptions": result.assumptions,
                "alternatives": result.alternatives
            }
            
            return json.dumps(response, indent=2)
            
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return json.dumps({
                "error": str(e),
                "sql": None,
                "confidence": "low"
            })
    
    def search_knowledge_graph(self, query: str) -> str:
        """
        Search the knowledge graph for entities, patterns, and schema.
        
        Use this to explore what's in the knowledge base before
        generating SQL, or to debug entity resolution.
        
        Args:
            query: Natural language query to search for
            
        Returns:
            JSON string with matched entities, patterns, and concepts
        """
        try:
            results = self.search_service.search_all(query)
            return json.dumps(results, indent=2, default=str)
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return json.dumps({"error": str(e)})
    
    def add_table_to_knowledge(
        self,
        table_name: str,
        columns: List[Dict[str, str]],
        description: Optional[str] = None,
        entity_name: Optional[str] = None,
        synonyms: Optional[List[str]] = None
    ) -> str:
        """
        Add a table and its columns to the knowledge graph.
        
        This helps the system understand your database schema.
        
        Args:
            table_name: Name of the table
            columns: List of column definitions with 'name', 'data_type', 'description'
            description: Table description
            entity_name: Business entity this table represents
            synonyms: Alternative names for the entity
            
        Returns:
            JSON confirmation of added elements
        """
        try:
            # Add table
            self.schema_manager.add_table(
                name=table_name,
                database=self.database,
                description=description
            )
            
            # Add columns
            for col in columns:
                self.schema_manager.add_column(
                    table_name=table_name,
                    database=self.database,
                    column_name=col.get("name"),
                    data_type=col.get("data_type", "STRING"),
                    description=col.get("description")
                )
            
            # Add entity mapping if provided
            if entity_name:
                self.schema_manager.add_entity(
                    name=entity_name,
                    domain="business",
                    synonyms=synonyms or [],
                    description=description
                )
                self.schema_manager.map_entity_to_table(
                    entity_name=entity_name,
                    table_name=table_name,
                    database=self.database
                )
                
                # Add terms for the entity
                self.schema_manager.add_term(
                    text=entity_name.lower(),
                    entity_name=entity_name,
                    synonyms=synonyms
                )
            
            return json.dumps({
                "success": True,
                "table": table_name,
                "columns_added": len(columns),
                "entity": entity_name
            })
            
        except Exception as e:
            logger.error(f"Failed to add table: {e}")
            return json.dumps({"error": str(e)})

    def add_query_example(
        self,
        natural_language: str,
        sql: str,
        validated: bool = True
    ) -> str:
        """
        Add a validated query example to the knowledge graph.

        This helps the system learn from correct NL-to-SQL translations.

        Args:
            natural_language: The natural language question
            sql: The correct SQL query
            validated: Whether this has been validated

        Returns:
            JSON confirmation
        """
        try:
            result = self.pipeline.learn_from_feedback(
                original_query=natural_language,
                corrected_sql=sql,
                validated=validated
            )
            return json.dumps({
                "success": True,
                "stored": result
            })
        except Exception as e:
            logger.error(f"Failed to add example: {e}")
            return json.dumps({"error": str(e)})

    def initialize_graph(self, populate_defaults: bool = True) -> str:
        """
        Initialize or reset the knowledge graph schema.

        Creates indexes and optionally populates default patterns.

        Args:
            populate_defaults: Whether to add default NL patterns

        Returns:
            JSON with initialization results
        """
        try:
            schema_result = self.schema_manager.initialize_schema()

            pattern_result = {}
            if populate_defaults:
                pattern_result = self.schema_manager.populate_default_patterns()

            return json.dumps({
                "success": True,
                "schema": schema_result,
                "patterns": pattern_result
            })
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return json.dumps({"error": str(e)})

    def get_table_schema(self, table_name: str) -> str:
        """
        Get the schema information for a specific table.

        Args:
            table_name: Name of the table

        Returns:
            JSON with table schema including columns and relationships
        """
        try:
            schema = self.search_service.get_schema_for_table(
                table_name,
                database=self.database
            )

            if schema:
                return json.dumps({
                    "table": schema.table_name,
                    "database": schema.database,
                    "description": schema.description,
                    "columns": schema.columns,
                    "foreign_keys": schema.foreign_keys
                }, indent=2)
            else:
                return json.dumps({"error": f"Table {table_name} not found"})

        except Exception as e:
            logger.error(f"Schema lookup failed: {e}")
            return json.dumps({"error": str(e)})


def create_graph_text2sql_tool(
    database: Optional[str] = None,
    auto_initialize: bool = True
) -> GraphText2SQLTool:
    """
    Factory function to create a GraphText2SQLTool instance.

    Args:
        database: Default database name
        auto_initialize: Whether to auto-initialize the graph

    Returns:
        Configured GraphText2SQLTool instance
    """
    return GraphText2SQLTool(
        database=database,
        auto_initialize=auto_initialize
    )
