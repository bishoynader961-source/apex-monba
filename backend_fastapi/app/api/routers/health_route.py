"""Health check endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from app.shared.schemas import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()
