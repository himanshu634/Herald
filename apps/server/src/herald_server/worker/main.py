"""arq worker: mailbox syncs, the triage pipeline, and the cron jobs that keep push alive.

Run: uv run arq herald_server.worker.main.WorkerSettings
"""

import contextlib
from typing import Any

from arq import ArqRedis, Retry
from arq.connections import RedisSettings
from arq.cron import cron
from arq.worker import func
from asyncer import asyncify
from redis.exceptions import LockNotOwnedError

from herald_server.connectors.base import RateLimited
from herald_server.mailboxes import active_mailbox_ids, renew_subscriptions
from herald_server.pipeline import process_email
from herald_server.queue import PROCESS_EMAIL_JOB, SYNC_MAILBOX_JOB
from herald_server.services import build_services
from herald_server.settings import get_settings
from herald_server.sync import sync_mailbox

settings = get_settings()


async def startup(ctx: dict[str, Any]) -> None:
    ctx["services"] = build_services(settings)


async def shutdown(ctx: dict[str, Any]) -> None:
    services = ctx["services"]
    await services.bus.close()
    await services.http.aclose()
    services.engine.dispose()


async def process_email_job(ctx: dict[str, Any], email_id: str) -> str:
    decision = await process_email(ctx["services"], email_id)
    return decision.route


async def sync_mailbox_job(ctx: dict[str, Any], mailbox_id: str) -> None:
    redis: ArqRedis = ctx["redis"]
    # One sync per mailbox at a time, across all workers: two at once would fetch from the
    # same cursor and race to store the same batch. The timeout frees the lock if this worker
    # dies mid-sync; it matches arq's default job timeout of 300 s.
    lock = redis.lock(f"herald:sync:{mailbox_id}", timeout=300)
    if not await lock.acquire(blocking=False):
        # A sync already running may have read history before this change arrived, so a rerun
        # is needed once it is done. The fixed job id collapses a burst of pushes into one
        # rerun: arq does not enqueue a job whose id is already queued.
        await redis.enqueue_job(
            SYNC_MAILBOX_JOB, mailbox_id, _job_id=f"sync-again:{mailbox_id}", _defer_by=10
        )
        return
    try:
        email_ids = await sync_mailbox(ctx["services"], mailbox_id)
    except RateLimited as exc:
        # The cursor did not move, so the retry reads the same changes again.
        raise Retry(defer=exc.retry_after) from exc
    finally:
        # A sync that ran past the lock timeout no longer owns the lock (it expired, and
        # another sync may hold it now). Nothing is left to release; failing here would
        # drop the triage of the mail this sync just stored.
        with contextlib.suppress(LockNotOwnedError):
            await lock.release()
    for email_id in email_ids:
        await redis.enqueue_job(PROCESS_EMAIL_JOB, email_id)


async def renew_subscriptions_job(ctx: dict[str, Any]) -> int:
    # Cross-tenant by design (cron): renews push for every active mailbox in every workspace.
    return await renew_subscriptions(ctx["services"])


async def catch_up_syncs_job(ctx: dict[str, Any]) -> int:
    # Cross-tenant by design (cron): syncs every active mailbox in every workspace. This picks
    # up mail whose push was lost, and mail of mailboxes whose subscription has lapsed.
    redis: ArqRedis = ctx["redis"]
    mailbox_ids = await asyncify(active_mailbox_ids)(ctx["services"])
    for mailbox_id in mailbox_ids:
        await redis.enqueue_job(SYNC_MAILBOX_JOB, mailbox_id)
    return len(mailbox_ids)


class WorkerSettings:
    functions = [
        func(process_email_job, name=PROCESS_EMAIL_JOB),
        # keep_result=0: with a stored result, arq refuses to enqueue the same _job_id again
        # until the result expires (an hour by default), so the "sync-again" rerun of a
        # mailbox would be dropped for an hour after its first run.
        func(sync_mailbox_job, name=SYNC_MAILBOX_JOB, keep_result=0, max_tries=5),
    ]
    cron_jobs = [
        cron(renew_subscriptions_job, hour={3}, minute={0}),
        cron(catch_up_syncs_job, minute={0, 15, 30, 45}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 20
