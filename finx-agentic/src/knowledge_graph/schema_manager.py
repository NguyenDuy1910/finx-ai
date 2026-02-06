import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from .falkordb_client import FalkorDBClient, get_falkordb_client

logger = logging.getLogger(__name__)


class GraphSchemaManager:
    """
    Manages the Text2SQL knowledge graph schema.
    
    Responsible for:
    - Creating graph schema (nodes, relationships, indexes)
    - Populating initial data (schema introspection, patterns)
    - Maintaining schema integrity
    """
    
    def __init__(self, client: Optional[FalkorDBClient] = None):
        """
        Initialize schema manager.
        
        Args:
            client: FalkorDB client instance (optional, uses singleton if not provided)
        """
        self.client = client or get_falkordb_client()
    
    def initialize_schema(self) -> Dict[str, Any]:
        """
        Initialize the graph schema with indexes and constraints.
        
        Returns:
            Dictionary with initialization results
        """
        results = {"indexes_created": 0, "errors": []}
        
        # Create indexes for each node type
        index_queries = [
            # Table node indexes
            "CREATE INDEX FOR (t:Table) ON (t.name)",
            "CREATE INDEX FOR (t:Table) ON (t.database)",
            
            # Column node indexes
            "CREATE INDEX FOR (c:Column) ON (c.name)",
            "CREATE INDEX FOR (c:Column) ON (c.data_type)",
            
            # Entity node indexes
            "CREATE INDEX FOR (e:Entity) ON (e.name)",
            "CREATE INDEX FOR (e:Entity) ON (e.domain)",
            
            # Term node indexes
            "CREATE INDEX FOR (t:Term) ON (t.text)",
            
            # NLPattern node indexes
            "CREATE INDEX FOR (p:NLPattern) ON (p.intent)",
            "CREATE INDEX FOR (p:NLPattern) ON (p.pattern)",
            
            # SQLTemplate node indexes
            "CREATE INDEX FOR (s:SQLTemplate) ON (s.name)",
            
            # QueryExample node indexes
            "CREATE INDEX FOR (q:QueryExample) ON (q.validated)",
            
            # Concept node indexes
            "CREATE INDEX FOR (c:Concept) ON (c.domain)",
        ]
        
        for query in index_queries:
            try:
                self.client.execute_write(query)
                results["indexes_created"] += 1
            except Exception as e:
                # Index might already exist
                if "already indexed" not in str(e).lower():
                    results["errors"].append(str(e))
        
        logger.info(f"Schema initialized: {results['indexes_created']} indexes created")
        return results
    
    def add_table(
        self,
        name: str,
        database: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Add a table node to the knowledge graph.
        
        Args:
            name: Table name
            database: Database name
            description: Optional table description
            metadata: Optional additional metadata
            
        Returns:
            Created node information
        """
        query = """
        MERGE (t:Table {name: $name, database: $database})
        SET t.description = $description,
            t.created_at = $created_at,
            t.metadata = $metadata
        RETURN t.name as name, t.database as database
        """
        
        params = {
            "name": name,
            "database": database,
            "description": description or "",
            "created_at": datetime.now().isoformat(),
            "metadata": str(metadata or {})
        }
        
        result = self.client.execute_query(query, params)
        logger.info(f"Added table: {database}.{name}")
        return result[0] if result else {}
    
    def add_column(
        self,
        table_name: str,
        database: str,
        column_name: str,
        data_type: str,
        description: Optional[str] = None,
        is_primary_key: bool = False,
        is_foreign_key: bool = False,
        references: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Add a column node and link it to its table.
        
        Args:
            table_name: Parent table name
            database: Database name
            column_name: Column name
            data_type: Column data type
            description: Optional column description
            is_primary_key: Whether column is a primary key
            is_foreign_key: Whether column is a foreign key
            references: Optional dict with 'table' and 'column' for FK reference
            
        Returns:
            Created relationship information
        """
        query = """
        MATCH (t:Table {name: $table_name, database: $database})
        MERGE (c:Column {name: $column_name, table: $table_name})
        SET c.data_type = $data_type,
            c.description = $description,
            c.is_primary_key = $is_pk,
            c.is_foreign_key = $is_fk
        MERGE (t)-[:HAS_COLUMN]->(c)
        RETURN t.name as table_name, c.name as column_name
        """
        
        params = {
            "table_name": table_name,
            "database": database,
            "column_name": column_name,
            "data_type": data_type,
            "description": description or "",
            "is_pk": is_primary_key,
            "is_fk": is_foreign_key
        }
        
        result = self.client.execute_query(query, params)
        
        # Add foreign key reference if provided
        if references and is_foreign_key:
            self._add_fk_reference(
                column_name, table_name,
                references.get("table"), references.get("column")
            )

        return result[0] if result else {}

    def _add_fk_reference(
        self,
        source_column: str,
        source_table: str,
        target_table: str,
        target_column: str
    ) -> None:
        """Add a foreign key reference relationship."""
        query = """
        MATCH (sc:Column {name: $source_column, table: $source_table})
        MATCH (tc:Column {name: $target_column, table: $target_table})
        MERGE (sc)-[:REFERENCES]->(tc)
        """
        self.client.execute_write(query, {
            "source_column": source_column,
            "source_table": source_table,
            "target_column": target_column,
            "target_table": target_table
        })

    def add_entity(
        self,
        name: str,
        domain: str,
        synonyms: List[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add a business entity node.

        Args:
            name: Entity name (e.g., "Customer", "Order")
            domain: Business domain (e.g., "sales", "finance")
            synonyms: List of alternative names
            description: Optional entity description

        Returns:
            Created node information
        """
        query = """
        MERGE (e:Entity {name: $name})
        SET e.domain = $domain,
            e.synonyms = $synonyms,
            e.description = $description
        RETURN e.name as name, e.domain as domain
        """

        params = {
            "name": name,
            "domain": domain,
            "synonyms": synonyms or [],
            "description": description or ""
        }

        result = self.client.execute_query(query, params)
        return result[0] if result else {}

    def map_entity_to_table(
        self,
        entity_name: str,
        table_name: str,
        database: str
    ) -> Dict[str, Any]:
        """Create a mapping from entity to table."""
        query = """
        MATCH (e:Entity {name: $entity_name})
        MATCH (t:Table {name: $table_name, database: $database})
        MERGE (e)-[:MAPS_TO]->(t)
        RETURN e.name as entity, t.name as table
        """
        result = self.client.execute_query(query, {
            "entity_name": entity_name,
            "table_name": table_name,
            "database": database
        })
        return result[0] if result else {}

    def add_term(
        self,
        text: str,
        entity_name: Optional[str] = None,
        synonyms: List[str] = None
    ) -> Dict[str, Any]:
        """
        Add a term (keyword) node.

        Args:
            text: The term text
            entity_name: Optional entity this term refers to
            synonyms: Optional list of synonym terms

        Returns:
            Created node information
        """
        query = """
        MERGE (t:Term {text: $text})
        SET t.normalized = toLower($text)
        RETURN t.text as text
        """

        result = self.client.execute_query(query, {"text": text})

        # Link to entity if provided
        if entity_name:
            self._link_term_to_entity(text, entity_name)

        # Create synonym relationships
        if synonyms:
            for synonym in synonyms:
                self._add_synonym(text, synonym)

        return result[0] if result else {}

    def _link_term_to_entity(self, term_text: str, entity_name: str) -> None:
        """Create a REFERS_TO relationship from term to entity."""
        query = """
        MATCH (t:Term {text: $term})
        MATCH (e:Entity {name: $entity})
        MERGE (t)-[:REFERS_TO]->(e)
        """
        self.client.execute_write(query, {"term": term_text, "entity": entity_name})

    def _add_synonym(self, term1: str, term2: str) -> None:
        """Create a SYNONYM_OF relationship between two terms."""
        # First ensure both terms exist
        self.client.execute_write(
            "MERGE (t:Term {text: $text}) SET t.normalized = toLower($text)",
            {"text": term2}
        )
        # Then create bidirectional synonym relationship
        query = """
        MATCH (t1:Term {text: $term1})
        MATCH (t2:Term {text: $term2})
        MERGE (t1)-[:SYNONYM_OF]->(t2)
        MERGE (t2)-[:SYNONYM_OF]->(t1)
        """
        self.client.execute_write(query, {"term1": term1, "term2": term2})

    def add_nl_pattern(
        self,
        pattern: str,
        intent: str,
        template_name: str,
        examples: List[str] = None,
        priority: int = 0
    ) -> Dict[str, Any]:
        """
        Add a natural language pattern with its SQL template.

        Args:
            pattern: Regex or keyword pattern to match
            intent: The intent type (e.g., "select_all", "count", "filter")
            template_name: Name of the linked SQL template
            examples: Example natural language phrases
            priority: Pattern matching priority (higher = more specific)

        Returns:
            Created pattern information
        """
        query = """
        MERGE (p:NLPattern {pattern: $pattern, intent: $intent})
        SET p.examples = $examples,
            p.priority = $priority
        WITH p
        MATCH (t:SQLTemplate {name: $template_name})
        MERGE (p)-[:GENERATES]->(t)
        RETURN p.pattern as pattern, p.intent as intent
        """

        result = self.client.execute_query(query, {
            "pattern": pattern,
            "intent": intent,
            "template_name": template_name,
            "examples": examples or [],
            "priority": priority
        })
        return result[0] if result else {}

    def add_sql_template(
        self,
        name: str,
        template: str,
        description: Optional[str] = None,
        placeholders: List[str] = None
    ) -> Dict[str, Any]:
        """
        Add a SQL template node.

        Args:
            name: Template name
            template: SQL template with placeholders (e.g., {table}, {columns})
            description: Template description
            placeholders: List of placeholder names in the template

        Returns:
            Created template information
        """
        query = """
        MERGE (s:SQLTemplate {name: $name})
        SET s.template = $template,
            s.description = $description,
            s.placeholders = $placeholders
        RETURN s.name as name
        """

        result = self.client.execute_query(query, {
            "name": name,
            "template": template,
            "description": description or "",
            "placeholders": placeholders or []
        })
        return result[0] if result else {}

    def add_query_example(
        self,
        natural_language: str,
        sql: str,
        validated: bool = False,
        tables_used: List[str] = None
    ) -> Dict[str, Any]:
        """
        Add a query example (historical NL-to-SQL pair).

        Args:
            natural_language: The natural language query
            sql: The corresponding SQL query
            validated: Whether the example has been validated
            tables_used: List of tables used in the query

        Returns:
            Created example information
        """
        query = """
        CREATE (q:QueryExample {
            natural_language: $nl,
            sql: $sql,
            validated: $validated,
            timestamp: $timestamp
        })
        RETURN q.natural_language as natural_language, q.validated as validated
        """

        result = self.client.execute_query(query, {
            "nl": natural_language,
            "sql": sql,
            "validated": validated,
            "timestamp": datetime.now().isoformat()
        })

        # Link to tables
        if tables_used:
            for table in tables_used:
                self._link_example_to_table(natural_language, table)

        return result[0] if result else {}

    def _link_example_to_table(self, nl: str, table_name: str) -> None:
        """Link a query example to a table."""
        query = """
        MATCH (q:QueryExample {natural_language: $nl})
        MATCH (t:Table {name: $table_name})
        MERGE (q)-[:TARGETS_TABLE]->(t)
        """
        self.client.execute_write(query, {"nl": nl, "table_name": table_name})

    def add_concept(
        self,
        name: str,
        domain: str,
        sql_expression: str,
        patterns: List[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add a semantic concept (e.g., temporal, quantitative).

        Args:
            name: Concept name (e.g., "last_month", "total")
            domain: Concept domain (e.g., "temporal", "aggregate")
            sql_expression: SQL translation (e.g., "INTERVAL '1 month'")
            patterns: Natural language patterns that match this concept
            description: Concept description

        Returns:
            Created concept information
        """
        query = """
        MERGE (c:Concept {name: $name, domain: $domain})
        SET c.sql_expression = $sql_expression,
            c.patterns = $patterns,
            c.description = $description
        RETURN c.name as name, c.domain as domain
        """

        result = self.client.execute_query(query, {
            "name": name,
            "domain": domain,
            "sql_expression": sql_expression,
            "patterns": patterns or [],
            "description": description or ""
        })
        return result[0] if result else {}

    def populate_default_patterns(self) -> Dict[str, int]:
        """
        Populate the graph with default NL patterns and SQL templates.

        Returns:
            Count of created patterns and templates
        """
        counts = {"templates": 0, "patterns": 0, "concepts": 0}

        # SQL Templates
        templates = [
            ("select_all", "SELECT * FROM {table}", "Select all rows from a table", ["table"]),
            ("select_columns", "SELECT {columns} FROM {table}", "Select specific columns", ["columns", "table"]),
            ("count_all", "SELECT COUNT(*) FROM {table}", "Count all rows", ["table"]),
            ("count_filtered", "SELECT COUNT(*) FROM {table} WHERE {condition}", "Count with filter", ["table", "condition"]),
            ("aggregate_sum", "SELECT SUM({column}) FROM {table}", "Sum a column", ["column", "table"]),
            ("aggregate_avg", "SELECT AVG({column}) FROM {table}", "Average a column", ["column", "table"]),
            ("group_by", "SELECT {group_col}, {agg_func}({agg_col}) FROM {table} GROUP BY {group_col}",
             "Aggregate with grouping", ["group_col", "agg_func", "agg_col", "table"]),
            ("join_tables", "SELECT {columns} FROM {table1} JOIN {table2} ON {join_condition}",
             "Join two tables", ["columns", "table1", "table2", "join_condition"]),
            ("filter_basic", "SELECT {columns} FROM {table} WHERE {condition}",
             "Filter with WHERE clause", ["columns", "table", "condition"]),
            ("order_limit", "SELECT {columns} FROM {table} ORDER BY {order_col} {order_dir} LIMIT {limit}",
             "Order and limit results", ["columns", "table", "order_col", "order_dir", "limit"]),
        ]

        for name, template, description, placeholders in templates:
            self.add_sql_template(name, template, description, placeholders)
            counts["templates"] += 1

        # NL Patterns
        patterns = [
            ("show me|list|display|get", "select", "select_all", ["show me all", "list the", "display"]),
            ("how many|count|number of", "count", "count_all", ["how many", "count the", "number of"]),
            ("total|sum of", "sum", "aggregate_sum", ["total sales", "sum of amounts"]),
            ("average|avg|mean", "average", "aggregate_avg", ["average price", "mean value"]),
            ("per|by|grouped by|for each", "group", "group_by", ["sales per customer", "orders by month"]),
            ("where|with|having|filter", "filter", "filter_basic", ["where status is", "with amount greater"]),
            ("top|first|limit", "limit", "order_limit", ["top 10", "first 5 results"]),
            ("and|with their|along with", "join", "join_tables", ["customers and their orders"]),
        ]

        for pattern, intent, template_name, examples in patterns:
            self.add_nl_pattern(pattern, intent, template_name, examples)
            counts["patterns"] += 1

        # Temporal Concepts
        concepts = [
            ("last_month", "temporal",
             "DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1' MONTH)",
             ["last month", "previous month"]),
            ("this_month", "temporal",
             "DATE_TRUNC('month', CURRENT_DATE)",
             ["this month", "current month"]),
            ("last_year", "temporal",
             "DATE_TRUNC('year', CURRENT_DATE - INTERVAL '1' YEAR)",
             ["last year", "previous year"]),
            ("this_year", "temporal",
             "EXTRACT(YEAR FROM CURRENT_DATE)",
             ["this year", "current year"]),
            ("yesterday", "temporal",
             "CURRENT_DATE - INTERVAL '1' DAY",
             ["yesterday"]),
            ("today", "temporal",
             "CURRENT_DATE",
             ["today"]),
        ]

        for name, domain, sql_expr, pats in concepts:
            self.add_concept(name, domain, sql_expr, pats)
            counts["concepts"] += 1

        logger.info(f"Populated default patterns: {counts}")
        return counts

