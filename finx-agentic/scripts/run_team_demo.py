from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.agentops_tracker import init_agentops

init_agentops(
    auto_start_session=True,
    tags=["finx-agentic", "finx-team"],
)

from agno.os import AgentOS

from src.knowledge.graph.client import get_graphiti_client
from src.storage.postgres import get_postgres_db
from src.teams.finx_team import build_finx_team

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

finx_team = build_finx_team(
    graphiti_client=client,
    database=database,
    output_location=athena_output,
    region_name=aws_region,
    db=pg_db,
)

agent_os = AgentOS(
    description="FinX Team",
    teams=[finx_team],
)
app = agent_os.get_app()

if __name__ == "__main__":
    agent_os.serve(
        app="run_team_demo:app",
        host="0.0.0.0",
        port=int(os.getenv("DEMO_PORT", "7777")),
    )
