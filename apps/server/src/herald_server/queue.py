"""Hand mailbox syncs and emails to background jobs. arq runs them in the worker; inline here."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, Protocol, Self

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from herald_server.pipeline import process_email
from herald_server.services import Services
from herald_server.sync import sync_mailbox

PROCESS_EMAIL_JOB = "process_email"
SYNC_MAILBOX_JOB = "sync_mailbox"

log = logging.getLogger(__name__)


class JobQueue(Protocol):
    async def enqueue_email(self, email_id: str) -> None: ...

    async def enqueue_sync(self, mailbox_id: str) -> None: ...

    async def close(self) -> None: ...


class ArqQueue:
    def __init__(self, pool: ArqRedis) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, redis_url: str) -> Self:
        return cls(await create_pool(RedisSettings.from_dsn(redis_url)))

    async def enqueue_email(self, email_id: str) -> None:
        await self._pool.enqueue_job(PROCESS_EMAIL_JOB, email_id)

    async def enqueue_sync(self, mailbox_id: str) -> None:
        await self._pool.enqueue_job(SYNC_MAILBOX_JOB, mailbox_id)

    async def close(self) -> None:
        await self._pool.aclose()


class InlineQueue:
    def __init__(self, services: Services) -> None:
        self._services = services
        self._tasks: set[asyncio.Task] = set()
        self._sync_locks: dict[str, asyncio.Lock] = {}

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def enqueue_email(self, email_id: str) -> None:
        self._spawn(process_email(self._services, email_id))

    async def enqueue_sync(self, mailbox_id: str) -> None:
        self._spawn(self._sync(mailbox_id))

    async def _sync(self, mailbox_id: str) -> None:
        # One sync per mailbox at a time: two at once would fetch from the same cursor and
        # race to store the same batch. A second request waits, then reads from the new cursor.
        lock = self._sync_locks.setdefault(mailbox_id, asyncio.Lock())
        async with lock:
            # has_more: the connector stopped at its per-fetch cap after storing a batch and
            # moving the cursor, so fetch again until the gap is read. Each batch moves the
            # cursor forward, so the loop ends.
            while True:
                try:
                    outcome = await sync_mailbox(self._services, mailbox_id)
                except Exception as exc:
                    # Inline has no retry (arq retries in the worker), so log and stop. The
                    # cursor did not move, so the next push or catch-up sync reads these
                    # changes again. Only the type name: str() of an HTTP error can carry
                    # provider responses.
                    log.warning("%s on sync of mailbox %s", type(exc).__name__, mailbox_id)
                    return
                # Queued per batch, so a failure on a later batch keeps the earlier ones triaged.
                for email_id in outcome.email_ids:
                    await self.enqueue_email(email_id)
                if not outcome.has_more:
                    return

    async def drain(self) -> None:
        """Wait for queued syncs and emails to finish (tests)."""
        # A sync adds its triage tasks to `_tasks` before it finishes, so looping until the
        # set is empty also waits for emails that a sync found.
        while self._tasks:
            await asyncio.gather(*self._tasks)

    async def close(self) -> None:
        await self.drain()
