from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.database import init_db
from app.routes import repos, stream, tasks

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()

    # Clean up orphaned containers from previous runs
    try:
        from app.services.container_manager import ContainerManager

        cm = ContainerManager()
        cm.cleanup_orphaned_containers()
    except Exception as exc:
        logger.warning("Container cleanup on startup failed: %s", exc)

    yield

    # Gracefully stop all active task containers on shutdown
    try:
        from app.services.container_manager import ContainerManager

        cm = ContainerManager()
        cm.cleanup_orphaned_containers()
    except Exception as exc:
        logger.warning("Container cleanup on shutdown failed: %s", exc)


settings = get_settings()
app = FastAPI(title="Orchestrator API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repos.router)
app.include_router(tasks.router)
app.include_router(stream.router)


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
