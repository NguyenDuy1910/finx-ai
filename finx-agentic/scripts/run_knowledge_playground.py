import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from agno.agent import Agent
from agno.os import AgentOS

from src.core.agentops_tracker import init_agentops

init_agentops(
    auto_start_session=False,
    tags=["finx-agentic", "knowledge-playground"],
)

from src.core.model_factory import create_model
from src.knowledge.client import get_graphiti_client
from src.tools.graph_tools import GraphSearchTools
from src.tools.athena_executor import AthenaExecutorTools
from src.prompts.manager import get_prompt_manager
from src.storage.postgres import get_postgres_db

host = os.getenv("FALKORDB_HOST", "localhost")
port = int(os.getenv("FALKORDB_PORT", "6379"))
database = os.getenv("ATHENA_DATABASE", "non_prod_uat_gold_zone")
athena_output = os.getenv("ATHENA_OUTPUT_LOCATION", "s3://aws-athena-query-results-889924997113-ap-southeast-1/")
aws_region = os.getenv("AWS_REGION", "ap-southeast-1")

client = get_graphiti_client(host=host, port=port)
graph_tools = GraphSearchTools(client=client, default_database=database)
athena_tools = AthenaExecutorTools(
    database=database,
    output_location=athena_output,
    region_name=aws_region,
)
pm = get_prompt_manager()
instructions = pm.render("knowledge/instructions.jinja2")

pg_db = get_postgres_db()

knowledge_agent = Agent(
    name="Knowledge Agent",
    model=create_model(),
    user_id="bodangdiet",
    instructions=[instructions],
    tools=[graph_tools, athena_tools],
    markdown=True,
    add_datetime_to_context=True,
    debug_mode=True,
    db=pg_db,
    # enable_user_memories=True,
    enable_session_summaries=True,
    add_history_to_context=True,
    num_history_runs=5,
)

agent_os = AgentOS(agents=[knowledge_agent])
app = agent_os.get_app()

if __name__ == "__main__":
    agent_os.serve(app="run_knowledge_playground:app", host="0.0.0.0", port=7777)
