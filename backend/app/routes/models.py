from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from app.agents.model_registry import get_available_models
from app.config import get_settings

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
async def list_models() -> list[dict]:
    settings = get_settings()
    return [asdict(m) for m in get_available_models(settings)]
