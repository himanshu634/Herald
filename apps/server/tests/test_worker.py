"""The arq sync job: per-mailbox lock, pending flag, retry on rate limit."""

import itertools
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from arq import Retry
from redis.exceptions import LockNotOwnedError
from sqlmodel import Session
from test_sync import add_mailbox, demo_workspace, message

from herald_server.connectors.base import RateLimited
from herald_server.models import Mailbox
from herald_server.queue import PROCESS_EMAIL_JOB, SYNC_MAILBOX_JOB
from herald_server.worker import main as worker_main
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
        if self.redis.before_release is not None:
            await self.redis.before_release()
        if self.name not in self.redis.held:
            raise LockNotOwnedError("lock expired")
        self.redis.held.remove(self.name)


class FakeRedis:
    """The ArqRedis calls the job makes, kept in memory and recorded instead of sent."""

    def __init__(self) -> None:
        self.held: set[str] = set()
        self.values: dict[str, Any] = {}
        self.enqueued: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.before_release: Callable[[], Awaitable[None]] | None = None

    def lock(self, name: str, timeout: float) -> FakeLock:
        assert timeout == worker_main.SYNC_LOCK_TTL
        return FakeLock(self, name)

    async def set(self, name: str, value: Any, ex: int | None = None) -> bool:
        assert ex == 3600
        self.values[name] = value
        return True

    async def getdel(self, name: str) -> Any:
        return self.values.pop(name, None)

    async def exists(self, name: str) -> int:
        return int(name in self.values)

    async def enqueue_job(self, function: str, *args: Any, **kwargs: Any) -> None:
        self.enqueued.append((function, args, kwargs))


def ctx_for(app) -> dict[str, Any]:
    return {"services": app.state.services, "redis": FakeRedis()}


def pending_key(mailbox_id: str) -> str:
    return f"herald:sync-pending:{mailbox_id}"


async def test_sync_job_queues_triage_and_releases_the_lock(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    fake_connector.queue = [message("m1")]
    ctx = ctx_for(app)

    await sync_mailbox_job(ctx, mailbox_id)

    [(function, args, kwargs)] = ctx["redis"].enqueued
    assert function == PROCESS_EMAIL_JOB and kwargs == {}
    assert ctx["redis"].held == set()
    assert ctx["redis"].values == {}


async def test_busy_lock_leaves_pending_flag_and_returns(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    ctx = ctx_for(app)
    ctx["redis"].held.add(f"herald:sync:{mailbox_id}")

    await sync_mailbox_job(ctx, mailbox_id)

    assert "fetch_changes" not in fake_connector.calls
    assert pending_key(mailbox_id) in ctx["redis"].values
    assert ctx["redis"].enqueued == []


async def test_push_during_sync_runs_again_in_same_job(app, client, monkeypatch):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    ctx = ctx_for(app)
    calls: list[str] = []

    async def fake_sync(services, synced_id: str) -> list[str]:
        calls.append(synced_id)
        if len(calls) == 1:
            # A push lands while this sync runs: its job finds the lock busy and sets the flag.
            await ctx["redis"].set(pending_key(mailbox_id), 1, ex=3600)
        return [f"email-{len(calls)}"]

    monkeypatch.setattr(worker_main, "sync_mailbox", fake_sync)

    await sync_mailbox_job(ctx, mailbox_id)

    assert calls == [mailbox_id, mailbox_id]
    assert ctx["redis"].enqueued == [
        (PROCESS_EMAIL_JOB, ("email-1",), {}),
        (PROCESS_EMAIL_JOB, ("email-2",), {}),
    ]
    assert ctx["redis"].values == {}


async def test_push_after_release_enqueues_fresh_sync(app, client, monkeypatch):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    ctx = ctx_for(app)

    async def fake_sync(services, synced_id: str) -> list[str]:
        return []

    async def push_arrives() -> None:
        # After the last GETDEL, before the release: the push's job saw the lock busy.
        await ctx["redis"].set(pending_key(mailbox_id), 1, ex=3600)

    monkeypatch.setattr(worker_main, "sync_mailbox", fake_sync)
    ctx["redis"].before_release = push_arrives

    await sync_mailbox_job(ctx, mailbox_id)

    assert ctx["redis"].enqueued == [(SYNC_MAILBOX_JOB, (mailbox_id,), {})]
    assert ctx["redis"].held == set()


async def test_busy_mailbox_stops_after_budget_and_hands_off(app, client, monkeypatch):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    ctx = ctx_for(app)
    calls: list[str] = []
    clock = itertools.count(0, 50)

    async def fake_sync(services, synced_id: str) -> list[str]:
        # A push lands during every sync, so the flag is never clear.
        calls.append(synced_id)
        await ctx["redis"].set(pending_key(mailbox_id), 1, ex=3600)
        return []

    monkeypatch.setattr(worker_main, "sync_mailbox", fake_sync)
    monkeypatch.setattr(worker_main, "monotonic", lambda: next(clock))

    await sync_mailbox_job(ctx, mailbox_id)

    # Budget 120 s, clock +50 s per read: syncs start at 50 s and 100 s, none at 150 s.
    assert len(calls) == 2
    assert ctx["redis"].enqueued == [(SYNC_MAILBOX_JOB, (mailbox_id,), {})]
    assert ctx["redis"].held == set()


async def test_expired_lock_does_not_fail_the_job(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    fake_connector.queue = [message("m1")]
    ctx = ctx_for(app)

    async def lock_expires() -> None:
        ctx["redis"].held.clear()

    ctx["redis"].before_release = lock_expires

    await sync_mailbox_job(ctx, mailbox_id)

    [(function, _, _)] = ctx["redis"].enqueued
    assert function == PROCESS_EMAIL_JOB


async def test_rate_limited_retries_after_at_least_5_seconds(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client), cursor="7")
    fake_connector.raise_on_fetch = RateLimited(0)
    ctx = ctx_for(app)

    with pytest.raises(Retry) as raised:
        await sync_mailbox_job(ctx, mailbox_id)

    assert raised.value.defer_score == 5_000
    assert ctx["redis"].held == set()
    with Session(app.state.services.engine) as session:
        mailbox = session.get(Mailbox, mailbox_id)
        assert mailbox is not None and mailbox.cursor == "7"


async def test_rate_limited_keeps_a_longer_retry_after(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    fake_connector.raise_on_fetch = RateLimited(30)

    with pytest.raises(Retry) as raised:
        await sync_mailbox_job(ctx_for(app), mailbox_id)

    assert raised.value.defer_score == 30_000


async def test_catch_up_queues_a_sync_per_active_mailbox(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    ctx = ctx_for(app)

    assert await catch_up_syncs_job(ctx) == 1

    assert ctx["redis"].enqueued == [(SYNC_MAILBOX_JOB, (mailbox_id,), {})]
