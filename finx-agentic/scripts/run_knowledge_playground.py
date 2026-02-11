import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

# from langtrace_python_sdk import langtrace

# langtrace.init(api_key=os.getenv("LANGTRACE_API_KEY"))

# ── Import agno BEFORE AgentOps init to avoid circular import ─────────
from agno.agent import Agent, RunOutput
from agno.os import AgentOS

# ── AgentOps observability ────────────────────────────────────────────
from src.core.agentops_tracker import init_agentops

init_agentops(
    auto_start_session=False,
    tags=["finx-agentic", "knowledge-playground"],
)

from src.core.model_factory import create_model
from src.core.cost_tracker import CostTracker
from src.knowledge.client import get_graphiti_client
from src.tools.graph_tools import GraphSearchTools
from src.tools.athena_executor import AthenaExecutorTools
from src.prompts.manager import get_prompt_manager

# ── cost-tracking hook ────────────────────────────────────────────────
tracker = CostTracker()


# def track_cost_hook(run_output: RunOutput, **kwargs):
#     """Post-hook: log token usage & estimated cost after every agent run."""
#     label = "run"
#     if run_output.input:
#         try:
#             label = str(run_output.input.input_content_string())[:50]
#         except Exception:
#             label = run_output.run_id or "run"
#     step = tracker.track(run_output, step=label)
#     tracker.print_summary()


# ── setup ─────────────────────────────────────────────────────────────
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

knowledge_agent = Agent(
    name="Knowledge Agent",
    model=create_model(),
    instructions=[instructions],
    tools=[graph_tools, athena_tools],
    markdown=True,
    add_datetime_to_context=True,
    # post_hooks=[track_cost_hook],
    debug_mode=True,
)

agent_os = AgentOS(agents=[knowledge_agent])
app = agent_os.get_app()

if __name__ == "__main__":
    agent_os.serve(app="run_knowledge_playground:app", host="0.0.0.0", port=7777)
