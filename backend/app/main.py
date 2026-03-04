from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.database import init_db
from app.routes import repos, stream, tasks


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


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
