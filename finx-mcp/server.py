from src.core.types import MCPConfig
from src.registry.registry import MCPRegistry
import os
import sys
from dotenv import load_dotenv

def main():
    try:
        # Load environment variables from .env file if it exists
        load_dotenv()
        
        print("Initializing Athena MCP server...", file=sys.stderr)
        
        registry = MCPRegistry()
        
        config = MCPConfig(
            name="athena",
            enabled=True,
            settings={
                "region": "ap-southeast-1",
                "database": "non_prod_uat_silver_zone",
                "output_location": "s3://aws-athena-query-results-889924997113-ap-southeast-1/",
            }
        )
        
        print("Creating Athena provider...", file=sys.stderr)
        # Create provider and get FastMCP instance
        provider = registry.create_provider("athena", config)
        mcp = provider.get_mcp_instance()
        
        print("Starting MCP server...", file=sys.stderr)
        
        if len(sys.argv) > 1 and sys.argv[1] == "--sse":
            host = os.getenv("MCP_HOST", "0.0.0.0")
            port = int(os.getenv("MCP_PORT", "8000"))
            print(f"Starting SSE server on http://{host}:{port}", file=sys.stderr)
            mcp.run(transport="sse", host=host, port=port)
        else:
            print("Starting stdio server (use --sse flag for HTTP endpoint)", file=sys.stderr)
            mcp.run()
    except Exception as e:
        print(f"Error starting server: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
