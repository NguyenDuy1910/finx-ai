"""
Graph-based Text2SQL Demo

This script demonstrates the semantic search and text-to-SQL
translation capabilities using FalkorDB knowledge graph.

Usage:
    python examples/graph_text2sql_demo.py

Prerequisites:
    - FalkorDB running on localhost:6379
    - Run: docker compose -f docker-build/docker-compose.yaml up -d falkordb
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge_graph import (
    FalkorDBClient,
    GraphSchemaManager,
    SemanticSearchService,
    Text2SQLPipeline,
    get_falkordb_client
)


def setup_demo_schema(manager: GraphSchemaManager, database: str = "demo_db"):
    
    # Initialize schema
    manager.initialize_schema()
    manager.populate_default_patterns()
    
    # Add sample tables
    tables = [
        ("customers", "Customer information", [
            ("customer_id", "INTEGER", "Primary key", True, False),
            ("name", "VARCHAR", "Customer full name", False, False),
            ("email", "VARCHAR", "Customer email address", False, False),
            ("created_at", "TIMESTAMP", "Account creation date", False, False),
            ("status", "VARCHAR", "Account status (active/inactive)", False, False),
        ]),
        ("orders", "Customer orders", [
            ("order_id", "INTEGER", "Primary key", True, False),
            ("customer_id", "INTEGER", "Foreign key to customers", False, True),
            ("order_date", "DATE", "Order placement date", False, False),
            ("total_amount", "DECIMAL", "Order total value", False, False),
            ("status", "VARCHAR", "Order status", False, False),
        ]),
        ("products", "Product catalog", [
            ("product_id", "INTEGER", "Primary key", True, False),
            ("name", "VARCHAR", "Product name", False, False),
            ("category", "VARCHAR", "Product category", False, False),
            ("price", "DECIMAL", "Unit price", False, False),
        ]),
    ]
    
    for table_name, description, columns in tables:
        manager.add_table(table_name, database, description)
        for col_name, data_type, col_desc, is_pk, is_fk in columns:
            refs = {"table": "customers", "column": "customer_id"} if is_fk and "customer_id" in col_name else None
            manager.add_column(
                table_name, database, col_name, data_type,
                col_desc, is_pk, is_fk, refs
            )
    
    # Add entities and mappings
    entities = [
        ("Customer", "sales", ["client", "user", "buyer"], "customers"),
        ("Order", "sales", ["purchase", "transaction"], "orders"),
        ("Product", "inventory", ["item", "goods", "merchandise"], "products"),
    ]
    
    for entity_name, domain, synonyms, table_name in entities:
        manager.add_entity(entity_name, domain, synonyms)
        manager.map_entity_to_table(entity_name, table_name, database)
        
        # Add terms
        manager.add_term(entity_name.lower(), entity_name, synonyms)
        for syn in synonyms:
            manager.add_term(syn, entity_name)
    
    # Add some example queries
    examples = [
        ("Show me all customers", "SELECT * FROM customers"),
        ("How many orders do we have?", "SELECT COUNT(*) FROM orders"),
        ("Total sales this month", "SELECT SUM(total_amount) FROM orders WHERE order_date >= DATE_TRUNC('month', CURRENT_DATE)"),
        ("List customers with their orders", "SELECT c.name, o.order_id, o.total_amount FROM customers c JOIN orders o ON c.customer_id = o.customer_id"),
    ]
    
    for nl, sql in examples:
        manager.add_query_example(nl, sql, validated=True, tables_used=["customers", "orders"])
    
    print("Demo schema setup complete!")


def run_demo_queries(pipeline: Text2SQLPipeline):
    """Run demo natural language queries."""
    print("\n🔍 Running demo queries...\n")
    
    queries = [
        "Show me all customers",
        "How many orders do we have?",
        "What is the total sales amount?",
        "List top 10 customers by order count",
        "Show customers from last month",
    ]
    
    for query in queries:
        print(f"Query: {query}")
        print("-" * 50)
        
        result = pipeline.translate(query)
        
        print(f"🔹 SQL:\n{result.sql}\n")
        print(f"🔹 Confidence: {result.confidence.value}")
        print(f"🔹 Explanation:\n{result.explanation}")
        
        if result.graph_path:
            print("🔹 Graph Path:")
            for path in result.graph_path:
                print(f"   - {path}")
        
        if result.assumptions:
            print("🔹 Assumptions:")
            for assumption in result.assumptions:
                print(f"   - {assumption}")
        
        print("\n" + "=" * 60 + "\n")


def main():
    """Main demo entry point."""
    print("=" * 60)
    print("  Graph-based Text2SQL Demo")
    print("  Using FalkorDB Knowledge Graph")
    print("=" * 60)
    
    try:
        # Connect to FalkorDB
        print("\n🔌 Connecting to FalkorDB...")
        client = get_falkordb_client()
        print(" Connected!")
        
        # Initialize components
        manager = GraphSchemaManager(client)
        pipeline = Text2SQLPipeline(client, "demo_db")
        
        # Set up demo schema
        setup_demo_schema(manager)
        
        # Run demo queries
        run_demo_queries(pipeline)
        
        print("\n✨ Demo complete!")
        
    except Exception as e:
        print(f"\n Error: {e}")
        print("\nMake sure FalkorDB is running:")
        print("  docker compose -f docker-build/docker-compose.yaml up -d falkordb")
        sys.exit(1)


if __name__ == "__main__":
    main()

