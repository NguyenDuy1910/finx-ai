from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_client, get_memory
from api.models.schemas import HealthResponse, StatsResponse
from src.knowledge.graph.client import GraphitiClient
from src.knowledge.memory import MemoryManager

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(client: GraphitiClient = Depends(get_client)):
    connected = await client.ping()
    return HealthResponse(
        status="ok" if connected else "degraded",
        graph_connected=connected,
    )


@router.get("/stats", response_model=StatsResponse)
async def stats(memory: MemoryManager = Depends(get_memory)):
    data = await memory.get_stats()
    return StatsResponse(**data)
