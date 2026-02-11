import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge import get_graphiti_client


async def main():
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    schema_dir = os.getenv("SCHEMA_DIR", str(Path(__file__).parent / "graph_schemas"))

    print(f"Connecting to FalkorDB at {host}:{port}")

    client = get_graphiti_client(host=host, port=port)

    print("Initializing indices and vector indexes...")
    await client.initialize()
    print("Indices initialized")

    print(f"Loading schemas from: {schema_dir}")
    stats = await client.load_to_graph(schema_dir)
    print(f"Loaded: {stats}")

    await client.close()
    print("Done")


if __name__ == "__main__":
    asyncio.run(main())
