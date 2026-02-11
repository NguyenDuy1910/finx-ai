import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge.client import get_graphiti_client


async def main():
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    schema_dir = Path(__file__).parent / "graph_schemas"
    database = os.getenv("ATHENA_DATABASE", "non_prod_uat_gold_zone")

    print(f"Connecting to FalkorDB at {host}:{port}")
    print(f"Loading schemas from: {schema_dir}")
    print(f"Database: {database}")
    print("-" * 40)

    client = get_graphiti_client(host=host, port=port)
    
    await client.initialize()
    print("Initialized graph indices and constraints")
    print("-" * 40)

    stats = await client.load_to_graph(
        schema_path=str(schema_dir),
        database=database
    )

    print("-" * 40)
    print(f"Load Statistics:")
    print(f"  Tables: {stats['tables']}")
    print(f"  Columns: {stats['columns']}")
    print(f"  Entities: {stats['entities']}")
    print(f"  Edges: {stats['edges']}")
    print("-" * 40)

    await client.close()
    print("Done")


if __name__ == "__main__":
    asyncio.run(main())
