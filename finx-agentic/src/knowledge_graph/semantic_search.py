"""
Semantic Search Service for Text2SQL Knowledge Graph

Provides graph-based semantic search functions including:
- Entity resolution from natural language
- Schema lookup with relationships
- Pattern matching for intent detection
- Similar query retrieval
- Synonym expansion
"""

import logging
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .falkordb_client import FalkorDBClient, get_falkordb_client

logger = logging.getLogger(__name__)


@dataclass
class EntityMatch:
    """Represents a matched entity from the knowledge graph."""
    entity_name: str
    table_name: str
    table_description: str = ""
    matched_term: str = ""
    confidence: float = 1.0


@dataclass
class PatternMatch:
    """Represents a matched NL pattern."""
    pattern: str
    intent: str
    template: str
    template_description: str = ""
    priority: int = 0


@dataclass
class SchemaInfo:
    """Schema information for a table."""
    table_name: str
    database: str
    description: str = ""
    columns: List[Dict[str, Any]] = field(default_factory=list)
    foreign_keys: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class QuerySimilarity:
    """A similar historical query."""
    natural_language: str
    sql: str
    similarity_score: float = 0.0


class SemanticSearchService:
    """
    Service for semantic search operations on the Text2SQL knowledge graph.
    
    Provides methods for:
    - Finding relevant entities from NL queries
    - Resolving synonyms and terms
    - Matching NL patterns to SQL templates
    - Retrieving similar past queries
    - Looking up schema information
    """
    
    def __init__(self, client: Optional[FalkorDBClient] = None):
        """
        Initialize semantic search service.
        
        Args:
            client: FalkorDB client instance
        """
        self.client = client or get_falkordb_client()
    
    def find_entities(self, query: str) -> List[EntityMatch]:
        """
        Find relevant entities from a natural language query.
        
        Searches for terms in the query that map to entities,
        and follows entity-to-table mappings.
        
        Args:
            query: Natural language query
            
        Returns:
            List of matched entities with their table mappings
        """
        # Normalize query for matching
        query_lower = query.lower()
        words = set(re.findall(r'\b\w+\b', query_lower))
        
        # Search for term matches and synonym matches
        cypher_query = """
        MATCH (term:Term)-[:REFERS_TO]->(entity:Entity)-[:MAPS_TO]->(table:Table)
        WHERE toLower(term.text) IN $words
           OR any(word IN $words WHERE toLower(term.text) CONTAINS word)
        RETURN DISTINCT 
            entity.name as entity_name,
            table.name as table_name,
            table.description as table_description,
            term.text as matched_term,
            1.0 as confidence
        
        UNION
        
        MATCH (entity:Entity)-[:MAPS_TO]->(table:Table)
        WHERE any(syn IN entity.synonyms WHERE toLower(syn) IN $words)
           OR any(word IN $words WHERE toLower(entity.name) CONTAINS word)
        RETURN DISTINCT
            entity.name as entity_name,
            table.name as table_name,
            table.description as table_description,
            entity.name as matched_term,
            0.9 as confidence
        """
        
        results = self.client.execute_query(cypher_query, {"words": list(words)})
        
        matches = []
        seen = set()
        for row in results:
            key = (row["entity_name"], row["table_name"])
            if key not in seen:
                seen.add(key)
                matches.append(EntityMatch(
                    entity_name=row["entity_name"],
                    table_name=row["table_name"],
                    table_description=row.get("table_description", ""),
                    matched_term=row.get("matched_term", ""),
                    confidence=row.get("confidence", 1.0)
                ))
        
        return sorted(matches, key=lambda x: -x.confidence)
    
    def get_schema_for_table(
        self,
        table_name: str,
        database: Optional[str] = None
    ) -> Optional[SchemaInfo]:
        """
        Get complete schema information for a table.
        
        Args:
            table_name: Name of the table
            database: Optional database name filter
            
        Returns:
            SchemaInfo with columns and foreign keys
        """
        # Build query with optional database filter
        db_filter = "AND t.database = $database" if database else ""
        
        query = f"""
        MATCH (t:Table {{name: $table_name}})
        {db_filter}
        OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
        OPTIONAL MATCH (c)-[:REFERENCES]->(ref:Column)<-[:HAS_COLUMN]-(ref_table:Table)
        RETURN t.name as table_name,
               t.database as database,
               t.description as description,
               collect(DISTINCT {{
                   column: c.name,
                   data_type: c.data_type,
                   description: c.description,
                   is_primary_key: c.is_primary_key,
                   is_foreign_key: c.is_foreign_key,
                   references_table: ref_table.name,
                   references_column: ref.name
               }}) as columns
        """
        
        params = {"table_name": table_name}
        if database:
            params["database"] = database
        
        results = self.client.execute_query(query, params)
        
        if not results:
            return None
        
        row = results[0]
        columns = [c for c in row.get("columns", []) if c.get("column")]
        
        # Extract foreign keys
        foreign_keys = [
            {
                "source_column": c["column"],
                "target_table": c["references_table"],
                "target_column": c["references_column"]
            }
            for c in columns
            if c.get("is_foreign_key") and c.get("references_table")
        ]
        
        return SchemaInfo(
            table_name=row["table_name"],
            database=row.get("database", ""),
            description=row.get("description", ""),
            columns=columns,
            foreign_keys=foreign_keys
        )

    def match_patterns(self, query: str) -> List[PatternMatch]:
        """
        Match natural language patterns to SQL templates.

        Args:
            query: Natural language query

        Returns:
            List of matched patterns with their SQL templates
        """
        query_lower = query.lower()

        cypher_query = """
        MATCH (p:NLPattern)-[:GENERATES]->(t:SQLTemplate)
        RETURN p.pattern as pattern,
               p.intent as intent,
               p.priority as priority,
               t.template as template,
               t.description as template_description
        """

        results = self.client.execute_query(cypher_query)

        matches = []
        for row in results:
            pattern = row.get("pattern", "")
            # Check if pattern matches query
            if self._pattern_matches(pattern, query_lower):
                matches.append(PatternMatch(
                    pattern=pattern,
                    intent=row.get("intent", ""),
                    template=row.get("template", ""),
                    template_description=row.get("template_description", ""),
                    priority=row.get("priority", 0)
                ))

        return sorted(matches, key=lambda x: -x.priority)

    def _pattern_matches(self, pattern: str, query: str) -> bool:
        """Check if a pattern matches a query."""
        # Pattern can be regex or pipe-separated keywords
        keywords = pattern.split("|")
        for keyword in keywords:
            keyword = keyword.strip().lower()
            if keyword and keyword in query:
                return True
        return False

    def find_similar_queries(
        self,
        query: str,
        limit: int = 5
    ) -> List[QuerySimilarity]:
        """
        Find similar historical queries.

        Uses keyword matching to find similar past NL-to-SQL examples.

        Args:
            query: Natural language query
            limit: Maximum number of results

        Returns:
            List of similar queries with their SQL
        """
        words = re.findall(r'\b\w{3,}\b', query.lower())

        if not words:
            return []

        # Build regex pattern for matching any word
        word_pattern = "|".join(words)

        cypher_query = """
        MATCH (q:QueryExample)
        WHERE q.natural_language =~ $pattern
        RETURN q.natural_language as natural_language,
               q.sql as sql,
               q.validated as validated
        ORDER BY q.timestamp DESC
        LIMIT $limit
        """

        results = self.client.execute_query(cypher_query, {
            "pattern": f".*({word_pattern}).*",
            "limit": limit
        })

        return [
            QuerySimilarity(
                natural_language=row["natural_language"],
                sql=row["sql"],
                similarity_score=1.0 if row.get("validated") else 0.8
            )
            for row in results
        ]

    def resolve_concept(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a semantic concept (e.g., temporal expression).

        Args:
            text: Text containing the concept

        Returns:
            Dict with concept name and SQL expression, or None
        """
        text_lower = text.lower()

        cypher_query = """
        MATCH (c:Concept)
        WHERE any(p IN c.patterns WHERE $text CONTAINS toLower(p))
        RETURN c.name as name,
               c.domain as domain,
               c.sql_expression as sql_expression,
               c.description as description
        """

        results = self.client.execute_query(cypher_query, {"text": text_lower})
        return results[0] if results else None

    def expand_synonyms(self, term: str) -> List[str]:
        """
        Get all synonyms for a term.

        Args:
            term: The term to expand

        Returns:
            List of synonym terms
        """
        cypher_query = """
        MATCH (t:Term {text: $term})-[:SYNONYM_OF*1..2]->(syn:Term)
        RETURN DISTINCT syn.text as synonym
        """

        results = self.client.execute_query(cypher_query, {"term": term})
        return [r["synonym"] for r in results]

    def get_join_path(
        self,
        table1: str,
        table2: str
    ) -> Optional[List[Dict[str, str]]]:
        """
        Find the join path between two tables using foreign keys.

        Args:
            table1: First table name
            table2: Second table name

        Returns:
            List of join conditions, or None if no path exists
        """
        cypher_query = """
        MATCH (t1:Table {name: $table1})-[:HAS_COLUMN]->(c1:Column)-[:REFERENCES]->(c2:Column)<-[:HAS_COLUMN]-(t2:Table {name: $table2})
        RETURN t1.name as table1, c1.name as column1,
               t2.name as table2, c2.name as column2

        UNION

        MATCH (t1:Table {name: $table1})<-[:HAS_COLUMN]-(c1:Column)<-[:REFERENCES]-(c2:Column)-[:HAS_COLUMN]->(t2:Table {name: $table2})
        RETURN t1.name as table1, c1.name as column1,
               t2.name as table2, c2.name as column2
        """

        results = self.client.execute_query(cypher_query, {
            "table1": table1,
            "table2": table2
        })

        if not results:
            return None

        return [
            {
                "table1": r["table1"],
                "column1": r["column1"],
                "table2": r["table2"],
                "column2": r["column2"],
                "condition": f"{r['table1']}.{r['column1']} = {r['table2']}.{r['column2']}"
            }
            for r in results
        ]

    def search_all(self, query: str) -> Dict[str, Any]:
        """
        Perform comprehensive semantic search on a natural language query.

        This is the main entry point that combines all search methods.

        Args:
            query: Natural language query

        Returns:
            Dictionary with all search results
        """
        return {
            "entities": [e.__dict__ for e in self.find_entities(query)],
            "patterns": [p.__dict__ for p in self.match_patterns(query)],
            "similar_queries": [q.__dict__ for q in self.find_similar_queries(query)],
            "concepts": self._find_all_concepts(query)
        }

    def _find_all_concepts(self, query: str) -> List[Dict[str, Any]]:
        """Find all concepts mentioned in the query."""
        text_lower = query.lower()

        cypher_query = """
        MATCH (c:Concept)
        RETURN c.name as name,
               c.domain as domain,
               c.sql_expression as sql_expression,
               c.patterns as patterns
        """

        results = self.client.execute_query(cypher_query)

        matches = []
        for row in results:
            patterns = row.get("patterns", [])
            if any(p.lower() in text_lower for p in patterns if p):
                matches.append({
                    "name": row["name"],
                    "domain": row["domain"],
                    "sql_expression": row["sql_expression"]
                })

        return matches
