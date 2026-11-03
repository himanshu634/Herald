"""Hand emails to the pipeline. arq runs them in the worker process; inline runs them here."""

import asyncio
from typing import Protocol, Self

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from herald_server.pipeline import process_email
from herald_server.services import Services

PROCESS_EMAIL_JOB = "process_email"


class JobQueue(Protocol):
    async def enqueue_email(self, email_id: str) -> None: ...

    async def close(self) -> None: ...


class ArqQueue:
    def __init__(self, pool: ArqRedis) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, redis_url: str) -> Self:
        return cls(await create_pool(RedisSettings.from_dsn(redis_url)))

    async def enqueue_email(self, email_id: str) -> None:
        await self._pool.enqueue_job(PROCESS_EMAIL_JOB, email_id)

    async def close(self) -> None:
        await self._pool.aclose()


class InlineQueue:
    def __init__(self, services: Services) -> None:
        self._services = services
        self._tasks: set[asyncio.Task] = set()

    async def enqueue_email(self, email_id: str) -> None:
        task = asyncio.create_task(process_email(self._services, email_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """Wait for queued emails to finish (tests)."""
        while self._tasks:
            await asyncio.gather(*self._tasks)

    async def close(self) -> None:
        await self.drain()
