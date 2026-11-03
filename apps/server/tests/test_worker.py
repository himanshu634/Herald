"""The arq sync job: per-mailbox lock, rerun on contention, retry on rate limit."""

from typing import Any

import pytest
from arq import Retry
from sqlmodel import Session
from test_sync import add_mailbox, demo_workspace, message

from herald_server.connectors.base import RateLimited
from herald_server.models import Mailbox
from herald_server.queue import PROCESS_EMAIL_JOB, SYNC_MAILBOX_JOB
from herald_server.worker.main import catch_up_syncs_job, sync_mailbox_job


class FakeLock:
    def __init__(self, redis: "FakeRedis", name: str) -> None:
        self.redis = redis
        self.name = name

    async def acquire(self, blocking: bool = True) -> bool:
        assert blocking is False
        if self.name in self.redis.held:
            return False
        self.redis.held.add(self.name)
        return True

    async def release(self) -> None:
        self.redis.held.remove(self.name)


class FakeRedis:
    """The two ArqRedis calls the job makes, recorded instead of sent."""

    def __init__(self) -> None:
        self.held: set[str] = set()
        self.enqueued: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def lock(self, name: str, timeout: float) -> FakeLock:
        assert timeout == 300
        return FakeLock(self, name)

    async def enqueue_job(self, function: str, *args: Any, **kwargs: Any) -> None:
        self.enqueued.append((function, args, kwargs))


def ctx_for(app) -> dict[str, Any]:
    return {"services": app.state.services, "redis": FakeRedis()}


async def test_sync_job_queues_triage_and_releases_the_lock(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    fake_connector.queue = [message("m1")]
    ctx = ctx_for(app)

    await sync_mailbox_job(ctx, mailbox_id)

    [(function, args, kwargs)] = ctx["redis"].enqueued
    assert function == PROCESS_EMAIL_JOB and kwargs == {}
    assert ctx["redis"].held == set()


async def test_sync_job_reruns_later_while_another_sync_holds_the_lock(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    ctx = ctx_for(app)
    ctx["redis"].held.add(f"herald:sync:{mailbox_id}")

    await sync_mailbox_job(ctx, mailbox_id)

    assert "fetch_changes" not in fake_connector.calls
    assert ctx["redis"].enqueued == [
        (SYNC_MAILBOX_JOB, (mailbox_id,), {"_job_id": f"sync-again:{mailbox_id}", "_defer_by": 10})
    ]


async def test_sync_job_retries_when_rate_limited(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client), cursor="7")
    fake_connector.raise_on_fetch = RateLimited(30)
    ctx = ctx_for(app)

    with pytest.raises(Retry) as raised:
        await sync_mailbox_job(ctx, mailbox_id)

    assert raised.value.defer_score == 30_000
    assert ctx["redis"].held == set()
    with Session(app.state.services.engine) as session:
        mailbox = session.get(Mailbox, mailbox_id)
        assert mailbox is not None and mailbox.cursor == "7"


async def test_catch_up_queues_a_sync_per_active_mailbox(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    ctx = ctx_for(app)

    assert await catch_up_syncs_job(ctx) == 1

    assert ctx["redis"].enqueued == [(SYNC_MAILBOX_JOB, (mailbox_id,), {})]
