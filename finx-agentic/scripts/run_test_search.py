import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge import get_graphiti_client, SemanticSearchService


async def main():
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))

    print(f"Connecting to FalkorDB at {host}:{port}")
    print("-" * 40)

    client = get_graphiti_client(host=host, port=port)
    search = SemanticSearchService(client)

    queries = [
        "show all customers active card info in 2025",
    ]

    if len(sys.argv) > 1:
        queries = [" ".join(sys.argv[1:])]

    for query in queries:
        print(f"\nQuery: {query}")
        print("-" * 40)

        result = await search.search_schema(query)

        if result.tables:
            print("Tables:")
            for t in result.tables:
                print(f"  [{t.score:.3f}] {t.name}: {t.summary}")

        if result.columns:
            print("Columns:")
            for c in result.columns:
                table = c.attributes.get("table_name", "")
                print(f"  [{c.score:.3f}] {table}.{c.name}: {c.summary}")

        if result.entities:
            print("Entities:")
            for e in result.entities:
                print(f"  [{e.score:.3f}] {e.name}: {e.summary}")

        if result.context:
            print("Context:")
            for ctx in result.context:
                cols = [col["name"] for col in ctx.get("columns", [])]
                print(f"  {ctx['database']}.{ctx['table']} -> columns: {', '.join(cols)}")

        print("=" * 40)

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
