# FinX AI - Deployment

Docker-based deployment for EKS and VM environments.

## Architecture

```
finx-ui (Next.js)  --->  finx-agentic (FastAPI)
     :3000                    :8080
                                |
                         +------+------+
                         |             |
                     PostgreSQL    FalkorDB
                       :5432        :6379
```

## Quick Start (Docker Compose)

```bash
cp .env.example .env    # fill in API keys
docker compose up -d
```

| Service      | URL                          |
| ------------ | ---------------------------- |
| FinX UI      | http://localhost:3000         |
| FinX API     | http://localhost:8080/docs    |
| FalkorDB UI  | http://localhost:3001         |
| PostgreSQL   | localhost:5432               |

## Build Images for Registry

```bash
# backend
docker build -f docker/api.Dockerfile -t finx-agentic:latest ../finx-agentic

# frontend
docker build -f docker/ui.Dockerfile -t finx-ui:latest ../finx-ui
```

Tag and push to ECR / any registry:

```bash
docker tag finx-agentic:latest <REGISTRY>/finx-agentic:latest
docker tag finx-ui:latest <REGISTRY>/finx-ui:latest
docker push <REGISTRY>/finx-agentic:latest
docker push <REGISTRY>/finx-ui:latest
```

## Deploy to EKS

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/
```

## Scripts

```bash
./scripts/start.sh          # start all services
./scripts/stop.sh           # stop all services
./scripts/logs.sh [service] # tail logs
./scripts/health.sh         # check service health
```

## Development

Start only databases locally, run apps with hot-reload:

```bash
docker compose up postgres falkordb -d

cd ../finx-agentic && uv run uvicorn src.web.app:app --host 0.0.0.0 --port 8080 --reload
cd ../finx-ui && npm run dev
```
