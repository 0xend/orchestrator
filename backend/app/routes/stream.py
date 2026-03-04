from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Task
from app.security.auth import AuthenticatedUser, get_current_user
from app.services.event_bus import event_bus

router = APIRouter(tags=["stream"])


def _sse_message(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/api/tasks/{task_id}/stream")
async def stream_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> StreamingResponse:
    result = await db.execute(
        select(Task.id).where(Task.id == task_id, Task.owner_user_id == current_user.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    async def generator():
        yield _sse_message("status_change", {"status": "connected", "task_id": task_id})
        async with event_bus.subscribe(task_id) as queue:
            while True:
                try:
                    envelope = await asyncio.wait_for(queue.get(), timeout=15)
                    yield _sse_message(envelope.event, envelope.data)
                except TimeoutError:
                    yield ": keepalive\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
