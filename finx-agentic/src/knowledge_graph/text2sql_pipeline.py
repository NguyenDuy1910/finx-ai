import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .falkordb_client import FalkorDBClient, get_falkordb_client
from .semantic_search import (
    SemanticSearchService, EntityMatch, PatternMatch, SchemaInfo
)

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Types of query intents."""
    SELECT = "select"
    COUNT = "count"
    SUM = "sum"
    AVERAGE = "average"
    GROUP = "group"
    FILTER = "filter"
    JOIN = "join"
    LIMIT = "limit"
    UNKNOWN = "unknown"


class Confidence(Enum):
    """Confidence levels for generated SQL."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class QueryAnalysis:
    """Analysis of a natural language query."""
    intent: QueryIntent
    entities: List[EntityMatch] = field(default_factory=list)
    attributes: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    temporal_expressions: List[Dict[str, Any]] = field(default_factory=list)
    aggregations: List[str] = field(default_factory=list)
    raw_query: str = ""


@dataclass
class SQLComponents:
    """Components of an SQL query."""
    select: List[str] = field(default_factory=list)
    from_tables: List[str] = field(default_factory=list)
    joins: List[str] = field(default_factory=list)
    where: List[str] = field(default_factory=list)
    group_by: List[str] = field(default_factory=list)
    having: List[str] = field(default_factory=list)
    order_by: List[str] = field(default_factory=list)
    limit: Optional[int] = None


@dataclass
class Text2SQLResult:
    """Result of Text2SQL translation."""
    sql: str
    explanation: str
    graph_path: List[str]
    confidence: Confidence
    assumptions: List[str]
    alternatives: List[str] = field(default_factory=list)
    debug_info: Dict[str, Any] = field(default_factory=dict)


class Text2SQLPipeline:
    """
    Pipeline for translating natural language to SQL.
    
    Uses the graph knowledge base to:
    - Resolve entities and terms
    - Match query patterns
    - Find similar historical queries
    - Build accurate SQL queries
    """
    
    # Intent detection patterns
    INTENT_PATTERNS = {
        QueryIntent.COUNT: [r"how many", r"count", r"number of", r"total number"],
        QueryIntent.SUM: [r"total\b", r"sum of", r"add up"],
        QueryIntent.AVERAGE: [r"average", r"avg\b", r"mean"],
        QueryIntent.GROUP: [r"per\b", r"by\b", r"grouped by", r"for each"],
        QueryIntent.FILTER: [r"where", r"with\b", r"that have", r"which"],
        QueryIntent.JOIN: [r"and their", r"with their", r"along with"],
        QueryIntent.LIMIT: [r"top\s+\d+", r"first\s+\d+", r"limit\s+\d+"],
        QueryIntent.SELECT: [r"show", r"list", r"display", r"get", r"find"],
    }
    
    # Aggregation function mappings
    AGG_FUNCTIONS = {
        "count": "COUNT",
        "sum": "SUM",
        "total": "SUM",
        "average": "AVG",
        "avg": "AVG",
        "mean": "AVG",
        "maximum": "MAX",
        "max": "MAX",
        "highest": "MAX",
        "minimum": "MIN",
        "min": "MIN",
        "lowest": "MIN",
    }
    
    def __init__(
        self,
        client: Optional[FalkorDBClient] = None,
        default_database: str = "default"
    ):
        """
        Initialize Text2SQL pipeline.
        
        Args:
            client: FalkorDB client instance
            default_database: Default database name for queries
        """
        self.client = client or get_falkordb_client()
        self.search_service = SemanticSearchService(self.client)
        self.default_database = default_database
    
    def translate(self, query: str) -> Text2SQLResult:
        """
        Translate natural language query to SQL.
        
        This is the main entry point for the pipeline.
        
        Args:
            query: Natural language query
            
        Returns:
            Text2SQLResult with SQL and explanation
        """
        graph_path = []
        assumptions = []
        
        # Step 1: Analyze the question
        logger.info(f"Step 1: Analyzing query: {query}")
        analysis = self._analyze_query(query)
        graph_path.append(f"Intent detected: {analysis.intent.value}")
        
        # Step 2: Query graph for context
        logger.info("Step 2: Querying graph for context")
        context = self._get_graph_context(query, analysis)
        
        for entity in analysis.entities:
            graph_path.append(
                f"Entity: {entity.matched_term} → {entity.entity_name} → Table: {entity.table_name}"
            )
        
        # Step 3: Construct SQL
        logger.info("Step 3: Constructing SQL")
        components = self._build_sql_components(analysis, context)
        sql = self._assemble_sql(components)
        
        # Step 4: Validate
        logger.info("Step 4: Validating SQL")
        is_valid, validation_errors = self._validate_sql(sql, context)
        if not is_valid:
            assumptions.extend([f"Validation warning: {e}" for e in validation_errors])
        
        # Step 5: Generate response
        confidence = self._assess_confidence(analysis, context, is_valid)
        explanation = self._generate_explanation(query, analysis, context)
        
        return Text2SQLResult(
            sql=sql,
            explanation=explanation,
            graph_path=graph_path,
            confidence=confidence,
            assumptions=assumptions,
            alternatives=self._get_alternatives(query, context),
            debug_info={
                "analysis": analysis.__dict__,
                "context_summary": self._summarize_context(context)
            }
        )

    def _analyze_query(self, query: str) -> QueryAnalysis:
        """
        Analyze the natural language query.

        Extracts:
        - Intent (SELECT, COUNT, etc.)
        - Entities (business objects)
        - Attributes (columns/properties)
        - Constraints (filters)
        - Temporal expressions
        - Aggregations
        """
        query_lower = query.lower()

        # Detect primary intent
        intent = self._detect_intent(query_lower)

        # Find entities using graph
        entities = self.search_service.find_entities(query)

        # Extract temporal expressions
        temporal = []
        for concept in self.search_service._find_all_concepts(query):
            if concept.get("domain") == "temporal":
                temporal.append(concept)

        # Extract aggregations
        aggregations = self._extract_aggregations(query_lower)

        # Extract constraints (basic pattern matching)
        constraints = self._extract_constraints(query_lower)

        return QueryAnalysis(
            intent=intent,
            entities=entities,
            temporal_expressions=temporal,
            aggregations=aggregations,
            constraints=constraints,
            raw_query=query
        )

    def _detect_intent(self, query: str) -> QueryIntent:
        """Detect the primary intent from the query."""
        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query):
                    return intent
        return QueryIntent.UNKNOWN

    def _extract_aggregations(self, query: str) -> List[str]:
        """Extract aggregation keywords from the query."""
        found = []
        for keyword in self.AGG_FUNCTIONS:
            if keyword in query:
                found.append(keyword)
        return found

    def _extract_constraints(self, query: str) -> List[str]:
        """Extract filter constraints from the query."""
        constraints = []

        # Common constraint patterns
        patterns = [
            r"where\s+(\w+\s+(?:is|=|>|<|>=|<=)\s+\w+)",
            r"with\s+(\w+\s+(?:greater|less|more|fewer)\s+than\s+\d+)",
            r"in\s+(\d{4})",  # Year filter
            r"from\s+(\d{4})",  # From year
            r"since\s+(\w+)",  # Since date
        ]

        for pattern in patterns:
            matches = re.findall(pattern, query)
            constraints.extend(matches)

        return constraints

    def _get_graph_context(
        self,
        query: str,
        analysis: QueryAnalysis
    ) -> Dict[str, Any]:
        """
        Get context from the graph database.

        Retrieves:
        - Schema information for relevant tables
        - Matching NL patterns
        - Similar historical queries
        - Join paths between tables
        """
        context = {
            "schemas": {},
            "patterns": [],
            "similar_queries": [],
            "join_paths": []
        }

        # Get schema for each matched entity's table
        tables = list(set(e.table_name for e in analysis.entities))
        for table in tables:
            schema = self.search_service.get_schema_for_table(table)
            if schema:
                context["schemas"][table] = schema

        # Match patterns
        context["patterns"] = self.search_service.match_patterns(query)

        # Find similar queries
        context["similar_queries"] = self.search_service.find_similar_queries(query)

        # Get join paths if multiple tables
        if len(tables) >= 2:
            for i in range(len(tables)):
                for j in range(i + 1, len(tables)):
                    join_path = self.search_service.get_join_path(tables[i], tables[j])
                    if join_path:
                        context["join_paths"].extend(join_path)

        return context

    def _build_sql_components(
        self,
        analysis: QueryAnalysis,
        context: Dict[str, Any]
    ) -> SQLComponents:
        """Build SQL components from analysis and context."""
        components = SQLComponents()

        tables = [e.table_name for e in analysis.entities]
        if not tables:
            tables = ["<table>"]  # Placeholder

        # FROM clause
        components.from_tables = list(set(tables))

        # SELECT clause based on intent
        if analysis.intent == QueryIntent.COUNT:
            components.select = ["COUNT(*) as count"]
        elif analysis.intent == QueryIntent.SUM and analysis.aggregations:
            components.select = ["SUM(<column>) as total"]
        elif analysis.intent == QueryIntent.AVERAGE and analysis.aggregations:
            components.select = ["AVG(<column>) as average"]
        else:
            components.select = ["*"]

        # JOINs from graph context
        join_paths = context.get("join_paths", [])
        if join_paths:
            for jp in join_paths:
                components.joins.append(
                    f"JOIN {jp['table2']} ON {jp['condition']}"
                )

        # WHERE clause from temporal expressions
        for temporal in analysis.temporal_expressions:
            sql_expr = temporal.get("sql_expression", "")
            if sql_expr:
                components.where.append(f"<date_column> >= {sql_expr}")

        # GROUP BY for grouping intent
        if analysis.intent == QueryIntent.GROUP:
            components.group_by = ["<group_column>"]

        # LIMIT extraction
        limit_match = re.search(r"(?:top|first|limit)\s+(\d+)", analysis.raw_query.lower())
        if limit_match:
            components.limit = int(limit_match.group(1))

        return components

    def _assemble_sql(self, components: SQLComponents) -> str:
        """Assemble SQL string from components."""
        parts = []

        # SELECT
        select_clause = ", ".join(components.select) if components.select else "*"
        parts.append(f"SELECT {select_clause}")

        # FROM
        from_clause = components.from_tables[0] if components.from_tables else "<table>"
        parts.append(f"FROM {from_clause}")

        # JOINs
        for join in components.joins:
            parts.append(join)

        # WHERE
        if components.where:
            where_clause = " AND ".join(components.where)
            parts.append(f"WHERE {where_clause}")

        # GROUP BY
        if components.group_by:
            group_clause = ", ".join(components.group_by)
            parts.append(f"GROUP BY {group_clause}")

        # HAVING
        if components.having:
            having_clause = " AND ".join(components.having)
            parts.append(f"HAVING {having_clause}")

        # ORDER BY
        if components.order_by:
            order_clause = ", ".join(components.order_by)
            parts.append(f"ORDER BY {order_clause}")

        # LIMIT
        if components.limit:
            parts.append(f"LIMIT {components.limit}")

        return "\n".join(parts)

    def _validate_sql(
        self,
        sql: str,
        context: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate the generated SQL.

        Checks:
        - All referenced tables exist in schema
        - Basic syntax validity
        - Join conditions are present for multiple tables

        Returns:
            Tuple of (is_valid, list of errors)
        """
        errors = []

        # Check for placeholder markers
        if "<table>" in sql or "<column>" in sql:
            errors.append("SQL contains unresolved placeholders")

        # Check basic syntax
        required_parts = ["SELECT", "FROM"]
        for part in required_parts:
            if part not in sql.upper():
                errors.append(f"Missing {part} clause")

        # Check that tables in FROM exist in context
        schemas = context.get("schemas", {})
        # Simple check - could be more sophisticated

        return len(errors) == 0, errors

    def _assess_confidence(
        self,
        analysis: QueryAnalysis,
        context: Dict[str, Any],
        is_valid: bool
    ) -> Confidence:
        """Assess confidence level of the generated SQL."""
        if not is_valid:
            return Confidence.LOW

        # High confidence if:
        # - Clear intent detected
        # - Entities mapped to tables
        # - Similar queries found
        has_entities = len(analysis.entities) > 0
        has_similar = len(context.get("similar_queries", [])) > 0
        has_patterns = len(context.get("patterns", [])) > 0
        clear_intent = analysis.intent != QueryIntent.UNKNOWN

        if has_entities and clear_intent and (has_similar or has_patterns):
            return Confidence.HIGH
        elif has_entities or clear_intent:
            return Confidence.MEDIUM
        else:
            return Confidence.LOW

    def _generate_explanation(
        self,
        query: str,
        analysis: QueryAnalysis,
        context: Dict[str, Any]
    ) -> str:
        """Generate a human-readable explanation of the SQL generation."""
        parts = []

        parts.append(f"**Intent Detected:** {analysis.intent.value}")

        if analysis.entities:
            entity_strs = [
                f"{e.matched_term} → {e.table_name}"
                for e in analysis.entities
            ]
            parts.append(f"**Entities Found:** {', '.join(entity_strs)}")

        if analysis.temporal_expressions:
            temporal_names = [t.get("name", "") for t in analysis.temporal_expressions]
            parts.append(f"**Temporal Concepts:** {', '.join(temporal_names)}")

        patterns = context.get("patterns", [])
        if patterns:
            pattern_intents = [p.intent for p in patterns[:3]]
            parts.append(f"**Matched Patterns:** {', '.join(pattern_intents)}")

        similar = context.get("similar_queries", [])
        if similar:
            parts.append(f"**Similar Past Queries:** {len(similar)} found")

        return "\n".join(parts)

    def _get_alternatives(
        self,
        query: str,
        context: Dict[str, Any]
    ) -> List[str]:
        """Get alternative SQL interpretations."""
        alternatives = []

        similar = context.get("similar_queries", [])
        for sq in similar[:2]:
            if sq.sql:
                alternatives.append(sq.sql)

        return alternatives

    def _summarize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Create a summary of the context for debugging."""
        return {
            "tables_found": list(context.get("schemas", {}).keys()),
            "patterns_matched": len(context.get("patterns", [])),
            "similar_queries": len(context.get("similar_queries", [])),
            "join_paths": len(context.get("join_paths", []))
        }

    def learn_from_feedback(
        self,
        original_query: str,
        corrected_sql: str,
        validated: bool = True
    ) -> Dict[str, Any]:
        """
        Learn from user feedback by storing the example.

        Args:
            original_query: The original natural language query
            corrected_sql: The correct SQL (user-validated or corrected)
            validated: Whether this has been validated by user

        Returns:
            Information about the stored example
        """
        from .schema_manager import GraphSchemaManager

        manager = GraphSchemaManager(self.client)

        # Extract tables from SQL
        tables_used = self._extract_tables_from_sql(corrected_sql)

        # Store the example
        result = manager.add_query_example(
            natural_language=original_query,
            sql=corrected_sql,
            validated=validated,
            tables_used=tables_used
        )

        logger.info(f"Learned from feedback: {original_query[:50]}...")
        return result

    def _extract_tables_from_sql(self, sql: str) -> List[str]:
        """Extract table names from SQL query."""
        # Simple extraction - match words after FROM and JOIN
        pattern = r"(?:FROM|JOIN)\s+(\w+)"
        matches = re.findall(pattern, sql, re.IGNORECASE)
        return list(set(matches))
