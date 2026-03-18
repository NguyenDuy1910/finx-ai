#!/bin/bash
set -e
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit it with your API keys, then re-run."
  exit 1
fi

docker compose up -d --build
echo ""
echo "  UI:   http://localhost:3000"
echo "  API:  http://localhost:8080/docs"
