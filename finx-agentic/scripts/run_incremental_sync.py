import asyncio
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge.graph.client import get_graphiti_client
from scripts.build_graph_schema.graph_updater import GraphUpdater
from scripts.build_graph_schema.incremental_sync import IncrementalSchemaSync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    database = os.getenv("ATHENA_DATABASE", "non_prod_uat_dbt_mart")
    region = os.getenv("AWS_REGION", "ap-southeast-1")
    profile = os.getenv("AWS_PROFILE")
    schema_dir = os.getenv("SCHEMA_DIR", str(Path(__file__).parent / "graph_schemas"))

    tables_env = os.getenv("TABLES")
    tables = tables_env.split(",") if tables_env else None
    cost_limit = float(os.getenv("COST_LIMIT_USD", "1.0"))
    max_concurrency = int(os.getenv("MAX_CONCURRENCY", "20"))

    logger.info(f"Database: {database}")
    logger.info(f"Schema dir: {schema_dir}")
    logger.info(f"FalkorDB: {host}:{port}")
    logger.info(f"Tables: {tables or 'all'}")
    logger.info(f"Cost limit: ${cost_limit:.2f}")
    logger.info(f"Max concurrency: {max_concurrency}")

    client = get_graphiti_client(host=host, port=port)
    await client.initialize()

    updater = GraphUpdater(client)
    sync = IncrementalSchemaSync(
        database=database,
        schema_dir=schema_dir,
        graph_updater=updater,
        region=region,
        profile=profile,
        cost_limit_usd=cost_limit,
        max_concurrency=max_concurrency,
    )

    result = await sync.sync(tables=tables)

    logger.info(f"Result: {result}")

    sync.generator.cost_tracker.print_summary()

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
