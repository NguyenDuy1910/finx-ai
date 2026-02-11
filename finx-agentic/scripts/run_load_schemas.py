import asyncio
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge_graph import get_graphiti_client, GraphSchemaManager


async def load_table_schema(manager, schema_data, database):
    table_name = schema_data["name"]
    db = schema_data.get("database", database)

    await manager.add_table(
        name=table_name,
        database=db,
        description=schema_data.get("description", ""),
    )

    for col in schema_data.get("columns", []):
        await manager.add_column(
            table_name=table_name,
            database=db,
            column_name=col["name"],
            data_type=col.get("type", "string"),
            description=col.get("description", ""),
            is_primary_key=col.get("primary_key", False),
            is_foreign_key=col.get("foreign_key", False),
        )

        for term in col.get("terms", []):
            await manager.add_term(
                text=term,
                entity_name=schema_data.get("entity", {}).get("name", table_name.title()),
            )

    entity = schema_data.get("entity", {})
    if entity:
        entity_name = entity.get("name", table_name.title())
        await manager.add_entity(
            name=entity_name,
            domain=entity.get("domain", "business"),
            synonyms=entity.get("synonyms", []),
            description=schema_data.get("description", ""),
        )
        await manager.map_entity_to_table(entity_name, table_name, db)
        await manager.add_term(
            text=entity_name.lower(),
            entity_name=entity_name,
            synonyms=entity.get("synonyms", []),
        )

    return table_name


async def main():
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    schema_dir = os.getenv("SCHEMA_DIR", "graph_schemas")
    database = os.getenv("ATHENA_DATABASE", "non_prod_uat_gold_zone")

    print(f"Connecting to FalkorDB at {host}:{port}")
    print(f"Loading schemas from: {schema_dir}")
    print(f"Database: {database}")
    print("-" * 40)

    client = get_graphiti_client(host=host, port=port)
    manager = GraphSchemaManager(client)

    schema_path = Path(schema_dir)
    if not schema_path.exists():
        print(f"Schema directory not found: {schema_dir}")
        sys.exit(1)

    json_files = list(schema_path.glob("*.json"))
    json_files = [f for f in json_files if not f.name.startswith("_")]

    print(f"Found {len(json_files)} schema files")
    print("-" * 40)

    loaded = []
    for json_file in json_files:
        print(f"Loading: {json_file.name}")
        with open(json_file) as f:
            schema_data = json.load(f)
        table_name = await load_table_schema(manager, schema_data, database)
        loaded.append(table_name)

    print("-" * 40)
    print(f"Loaded {len(loaded)} tables:")
    for t in loaded:
        print(f"  {t}")

    await client.close()
    print("Done")


if __name__ == "__main__":
    asyncio.run(main())
