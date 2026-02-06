import json
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

from .schema_manager import GraphSchemaManager
from .falkordb_client import FalkorDBClient, get_falkordb_client

logger = logging.getLogger(__name__)


class SchemaLoader:
    
    def __init__(
        self,
        client: Optional[FalkorDBClient] = None,
        database: str = "default"
    ):
        """
        Initialize schema loader.
        
        Args:
            client: FalkorDB client instance
            database: Default database name
        """
        self.client = client or get_falkordb_client()
        self.manager = GraphSchemaManager(self.client)
        self.database = database
    
    def load_from_athena(
        self,
        database: str,
        region: str = "us-east-1",
        catalog: str = "AwsDataCatalog",
        profile: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Load schema from AWS Athena metadata.
        
        Args:
            database: Athena database name
            region: AWS region
            catalog: Data catalog name
            profile: Optional AWS profile name
            
        Returns:
            Summary of loaded schema
        """
        try:
            import boto3
        except ImportError:
            raise ImportError("boto3 is required for Athena integration")
        
        logger.info(f"Loading schema from Athena database: {database}")
        
        # Create Athena client
        if profile:
            session = boto3.Session(profile_name=profile, region_name=region)
            client = session.client("athena")
            glue = session.client("glue")
        else:
            client = boto3.client("athena", region_name=region)
            glue = boto3.client("glue", region_name=region)
        
        stats = {"tables": 0, "columns": 0}
        
        # Get tables from Glue (Athena uses Glue Data Catalog)
        try:
            paginator = glue.get_paginator("get_tables")
            for page in paginator.paginate(DatabaseName=database):
                for table in page.get("TableList", []):
                    table_name = table["Name"]
                    description = table.get("Description", "")
                    
                    # Add table
                    self.manager.add_table(
                        name=table_name,
                        database=database,
                        description=description
                    )
                    stats["tables"] += 1
                    
                    # Add columns
                    for col in table.get("StorageDescriptor", {}).get("Columns", []):
                        self.manager.add_column(
                            table_name=table_name,
                            database=database,
                            column_name=col["Name"],
                            data_type=col.get("Type", "string"),
                            description=col.get("Comment", "")
                        )
                        stats["columns"] += 1
                    
                    # Add partition columns
                    for col in table.get("PartitionKeys", []):
                        self.manager.add_column(
                            table_name=table_name,
                            database=database,
                            column_name=col["Name"],
                            data_type=col.get("Type", "string"),
                            description=f"Partition key: {col.get('Comment', '')}"
                        )
                        stats["columns"] += 1
                        
        except Exception as e:
            logger.error(f"Error loading from Athena: {e}")
            raise
        
        logger.info(f"Loaded {stats['tables']} tables with {stats['columns']} columns")
        return stats
    
    def load_from_json(self, json_path: str) -> Dict[str, Any]:
        """
        Load schema from a JSON file.
        
        Expected format:
        {
            "database": "my_db",
            "tables": [
                {
                    "name": "table_name",
                    "description": "...",
                    "columns": [
                        {"name": "col1", "type": "string", "description": "..."}
                    ],
                    "entity": {
                        "name": "EntityName",
                        "domain": "business",
                        "synonyms": ["alt1", "alt2"]
                    }
                }
            ]
        }
        
        Args:
            json_path: Path to JSON schema file
            
        Returns:
            Summary of loaded schema
        """
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"Schema file not found: {json_path}")
        
        with open(path) as f:
            schema = json.load(f)
        
        return self.load_from_dict(schema)

    def load_from_dict(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Load schema from a dictionary.

        Args:
            schema: Schema dictionary

        Returns:
            Summary of loaded schema
        """
        database = schema.get("database", self.database)
        stats = {"tables": 0, "columns": 0, "entities": 0}

        for table_def in schema.get("tables", []):
            table_name = table_def["name"]

            # Add table
            self.manager.add_table(
                name=table_name,
                database=database,
                description=table_def.get("description", "")
            )
            stats["tables"] += 1

            # Add columns
            for col in table_def.get("columns", []):
                is_pk = col.get("primary_key", False)
                is_fk = col.get("foreign_key", False)
                refs = col.get("references")

                self.manager.add_column(
                    table_name=table_name,
                    database=database,
                    column_name=col["name"],
                    data_type=col.get("type", "string"),
                    description=col.get("description", ""),
                    is_primary_key=is_pk,
                    is_foreign_key=is_fk,
                    references=refs
                )
                stats["columns"] += 1

            # Add entity mapping if defined
            entity_def = table_def.get("entity")
            if entity_def:
                entity_name = entity_def["name"]
                self.manager.add_entity(
                    name=entity_name,
                    domain=entity_def.get("domain", "business"),
                    synonyms=entity_def.get("synonyms", []),
                    description=entity_def.get("description", "")
                )
                self.manager.map_entity_to_table(entity_name, table_name, database)

                # Add terms
                self.manager.add_term(
                    text=entity_name.lower(),
                    entity_name=entity_name,
                    synonyms=entity_def.get("synonyms", [])
                )
                stats["entities"] += 1

        logger.info(f"Loaded schema: {stats}")
        return stats

    def load_entity_mappings(
        self,
        mappings: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Load entity-to-table mappings.

        Args:
            mappings: List of entity mapping definitions
                [{"entity": "Customer", "table": "customers",
                  "synonyms": ["client"], "domain": "sales"}]

        Returns:
            Count of entities added
        """
        count = 0

        for mapping in mappings:
            entity_name = mapping["entity"]
            table_name = mapping["table"]

            # Create entity
            self.manager.add_entity(
                name=entity_name,
                domain=mapping.get("domain", "business"),
                synonyms=mapping.get("synonyms", []),
                description=mapping.get("description", "")
            )

            # Map to table
            self.manager.map_entity_to_table(
                entity_name, table_name, self.database
            )

            # Add terms
            self.manager.add_term(
                text=entity_name.lower(),
                entity_name=entity_name,
                synonyms=mapping.get("synonyms", [])
            )

            count += 1

        return {"entities_added": count}
