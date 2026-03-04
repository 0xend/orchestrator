from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import AsyncIterator


@dataclass(slots=True)
class EventEnvelope:
    event: str
    data: dict
    created_at: str


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[EventEnvelope]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(self, task_id: str, event: str, data: dict) -> None:
        envelope = EventEnvelope(
            event=event,
            data=data,
            created_at=datetime.now(UTC).isoformat(),
        )
        async with self._lock:
            subscribers = list(self._subscribers.get(task_id, set()))
        for queue in subscribers:
            await queue.put(envelope)

    @asynccontextmanager
    async def subscribe(self, task_id: str) -> AsyncIterator[asyncio.Queue[EventEnvelope]]:
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()
        async with self._lock:
            self._subscribers[task_id].add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                self._subscribers[task_id].discard(queue)
                if not self._subscribers[task_id]:
                    del self._subscribers[task_id]


event_bus = EventBus()
