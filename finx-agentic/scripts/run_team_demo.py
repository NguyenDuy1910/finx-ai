from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── AgentOps observability (must be initialised early) ────────────────
from src.core.agentops_tracker import init_agentops

init_agentops(
    auto_start_session=True,
    tags=["finx-agentic", "finx-team-demo"],
)

from agno.os import AgentOS

from src.knowledge.graph.client import get_graphiti_client
from src.storage.postgres import get_postgres_db
from src.teams.finx_team import build_finx_team
from src.tools.athena_executor import AthenaExecutorTools
from src.tools.graph_tools import GraphSearchTools

host = os.getenv("FALKORDB_HOST", "localhost")
port = int(os.getenv("FALKORDB_PORT", "6379"))
database = os.getenv("ATHENA_DATABASE", "non_prod_uat_gold_zone")
athena_output = os.getenv(
    "ATHENA_OUTPUT_LOCATION",
    "s3://aws-athena-query-results-889924997113-ap-southeast-1/",
)
aws_region = os.getenv("AWS_REGION", "ap-southeast-1")

client = get_graphiti_client(host=host, port=port)
pg_db = get_postgres_db()

graph_tools = GraphSearchTools(
    client=client,
    default_database=database,
)

athena_tools = AthenaExecutorTools(
    database=database,
    output_location=athena_output,
    region_name=aws_region,
)

finx_team = build_finx_team(
    graphiti_client=client,
    graph_tools=graph_tools,
    athena_tools=athena_tools,
    database=database,
    db=pg_db,
)

serve_port = int(os.getenv("DEMO_PORT", "7777"))

agent_os = AgentOS(
    description="FinX Team - Knowledge, SQL Generation, Validation, Execution",
    teams=[finx_team],
)
app = agent_os.get_app()

if __name__ == "__main__":
    agent_os.serve(
        app="run_team_demo:app",
        host="0.0.0.0",
        port=serve_port,
    )
