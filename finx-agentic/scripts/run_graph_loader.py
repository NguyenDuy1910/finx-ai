import asyncio
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge.client import get_graphiti_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    schema_dir = Path(__file__).parent / "graph_schemas"
    database = os.getenv("ATHENA_DATABASE", "non_prod_uat_dbt_mart")
    skip_existing = os.getenv("SKIP_EXISTING", "true").lower() in ("1", "true", "yes")

    logger.info(f"FalkorDB: {host}:{port}")
    logger.info(f"Database: {database}")
    logger.info(f"Schema dir: {schema_dir}")
    logger.info(f"Skip existing: {skip_existing}")
    logger.info("-" * 40)

    client = get_graphiti_client(host=host, port=port)
    await client.initialize()
    logger.info("Initialized graph indices and constraints")
    logger.info("-" * 40)

    stats = await client.load_to_graph(
        schema_path=str(schema_dir),
        database=database,
        skip_existing=skip_existing,
    )

    logger.info("-" * 40)
    logger.info("Load Statistics:")
    logger.info(f"  Tables loaded: {stats['tables']}")
    logger.info(f"  Tables skipped: {stats.get('skipped', 0)}")
    logger.info(f"  Columns: {stats['columns']}")
    logger.info(f"  Entities: {stats['entities']}")
    logger.info(f"  Domains: {stats.get('domains', 0)}")
    logger.info(f"  CodeSets: {stats.get('codesets', 0)}")
    logger.info(f"  Edges: {stats['edges']}")
    logger.info("-" * 40)

    client.cost_tracker.print_summary()

    await client.close()
    logger.info("Done")


if __name__ == "__main__":
    asyncio.run(main())
