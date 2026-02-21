from fastapi import APIRouter

from src.web.v1.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok", version="1.0.0")
