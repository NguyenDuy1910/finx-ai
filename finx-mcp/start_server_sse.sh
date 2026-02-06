#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8000}"

echo "Working directory: $SCRIPT_DIR"
echo "Starting Athena MCP server with SSE transport..."
echo "URL: http://${MCP_HOST}:${MCP_PORT}"
echo ""

uv run python server.py --sse
