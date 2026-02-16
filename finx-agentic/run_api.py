import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

import uvicorn

from src.web.app import create_app

# create_app() now returns an AgentOS-enhanced FastAPI app.
# All native AgentOS routes (agent runs, workflows, sessions, etc.)
# are merged automatically alongside your custom /api/v1/* routes.
app = create_app()

if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8080"))
    uvicorn.run(
        "run_api:app",
        host=host,
        port=port,
        reload=True,
    )
