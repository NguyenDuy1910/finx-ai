import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.knowledge import create_knowledge_agent
from src.core.cost_tracker import CostTracker
from src.knowledge.graph.client import get_graphiti_client
from src.tools.graph_tools import GraphSearchTools


async def main():
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    database = os.getenv("ATHENA_DATABASE", "non_prod_uat_gold_zone")

    client = get_graphiti_client(host=host, port=port)
    graph_tools = GraphSearchTools(client=client, default_database=database)
    agent = create_knowledge_agent(graph_tools=graph_tools)

    queries = [
        "find tables related to card transactions",
        "what columns does vk_card_tnx_batch have?",
        "resolve business term: giao dich the",
    ]

    if len(sys.argv) > 1:
        queries = [" ".join(sys.argv[1:])]

    tracker = CostTracker()

    for query in queries:
        print(f"\nQ: {query}")
        print("-" * 60)
        response = await agent.arun(query)
        tracker.track(response, step=query[:40])
        print(response.content)
        print("=" * 60)

    tracker.print_summary()

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
