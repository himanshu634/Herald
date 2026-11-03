"""Fan-out of workspace events to every open SSE stream.

One channel per workspace, so a tab only hears its own business. Redis lets several API
processes share events; the in-memory bus serves tests and single-process runs.
"""

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel
from redis.asyncio import Redis


class BusEvent(BaseModel):
    id: int
    workspace_id: str
    type: str
    data: dict[str, Any]
    created_at: datetime


class EventBus(Protocol):
    async def publish(self, event: BusEvent) -> None: ...

    def subscribe(self, workspace_id: str) -> Any:
        """An async context manager that yields an async iterator of BusEvent."""
        ...

    async def close(self) -> None: ...


def channel(workspace_id: str) -> str:
    return f"herald:ws:{workspace_id}"


class InMemoryEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[BusEvent]]] = defaultdict(set)

    async def publish(self, event: BusEvent) -> None:
        for queue in self._subscribers[event.workspace_id]:
            queue.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self, workspace_id: str) -> AsyncIterator[AsyncIterator[BusEvent]]:
        queue: asyncio.Queue[BusEvent] = asyncio.Queue()
        self._subscribers[workspace_id].add(queue)

        async def events() -> AsyncIterator[BusEvent]:
            while True:
                yield await queue.get()

        try:
            yield events()
        finally:
            self._subscribers[workspace_id].discard(queue)

    async def close(self) -> None:
        self._subscribers.clear()


class RedisEventBus:
    def __init__(self, url: str) -> None:
        self._redis = Redis.from_url(url)

    async def publish(self, event: BusEvent) -> None:
        await self._redis.publish(channel(event.workspace_id), event.model_dump_json())

    @asynccontextmanager
    async def subscribe(self, workspace_id: str) -> AsyncIterator[AsyncIterator[BusEvent]]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel(workspace_id))

        async def events() -> AsyncIterator[BusEvent]:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield BusEvent.model_validate_json(message["data"])

        try:
            yield events()
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    async def close(self) -> None:
        await self._redis.aclose()
