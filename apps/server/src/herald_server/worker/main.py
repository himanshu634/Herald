"""arq worker: mailbox syncs, the triage pipeline, and the cron jobs that keep push alive.

Run: uv run arq herald_server.worker.main.WorkerSettings
"""

import contextlib
from time import monotonic
from typing import Any

from arq import ArqRedis, Retry
from arq.connections import RedisSettings
from arq.cron import cron
from arq.worker import func
from asyncer import asyncify
from redis.exceptions import LockNotOwnedError

from herald_server.connectors.base import RateLimited
from herald_server.internal.client import AgentApi, ApiUnavailable
from herald_server.internal.token import internal_token
from herald_server.logs import setup_logging
from herald_server.mailboxes import active_mailbox_ids, renew_subscriptions
from herald_server.pipeline import process_email
from herald_server.queue import PROCESS_EMAIL_JOB, SYNC_MAILBOX_JOB
from herald_server.services import build_services
from herald_server.settings import get_settings
from herald_server.sync import sync_mailbox

settings = get_settings()

# Seconds. The sync lock's timeout and the worker's job timeout: a job that arq has cut off
# no longer holds the lock, so the next sync of that mailbox is not blocked for long.
SYNC_LOCK_TTL = 300
# Seconds. How long one job keeps re-syncing a busy mailbox before it hands off. Well under
# SYNC_LOCK_TTL: arq cancels a job at the job timeout, and a cancel that lands after a batch
# is committed but before its triage jobs are queued leaves that mail untriaged for good.
SYNC_LOOP_BUDGET = 120
# Seconds. A pending flag nobody consumed (e.g. the job failed) expires; the catch-up sync
# covers that mailbox meanwhile.
SYNC_PENDING_TTL = 3600
# Tries and seconds per try for a triage job whose API call failed safely (see ApiUnavailable).
PROCESS_EMAIL_TRIES = 5
API_RETRY_DEFER = 5


async def startup(ctx: dict[str, Any]) -> None:
    # Here, not at import: the arq CLI sets up its own logging after it imports this module.
    setup_logging(settings.log_level)
    ctx["services"] = build_services(settings)
    # The worker never makes up a token: one the API does not share would fail every email.
    ctx["agent_api"] = AgentApi.connect(
        settings.internal_api_url, internal_token(settings, allow_random=False)
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["agent_api"].close()
    services = ctx["services"]
    await services.bus.close()
    await services.http.aclose()
    services.engine.dispose()


async def process_email_job(ctx: dict[str, Any], email_id: str) -> str:
    try:
        decision = await process_email(ctx["agent_api"], ctx["services"].graph, email_id)
    except ApiUnavailable as exc:
        # The API is down or still starting (make dev starts it beside the worker), and
        # nothing was saved. arq does not retry a plain error, so without this the email
        # would stay "new" for good. Each try waits longer.
        raise Retry(defer=API_RETRY_DEFER * ctx["job_try"]) from exc
    return decision.route


async def sync_mailbox_job(ctx: dict[str, Any], mailbox_id: str) -> None:
    redis: ArqRedis = ctx["redis"]
    pending_key = f"herald:sync-pending:{mailbox_id}"
    # The flag records "something changed in this mailbox" even when the lock is busy, so no
    # push is lost: whoever holds the lock sees the flag and syncs again. Nothing depends on
    # arq's job-id dedupe, which refuses an id while that job runs or keeps a result.
    await redis.set(pending_key, 1, ex=SYNC_PENDING_TTL)
    # One sync per mailbox at a time, across all workers: two at once would fetch from the
    # same cursor and race to store the same batch. The timeout frees the lock if this worker
    # dies mid-sync.
    lock = redis.lock(f"herald:sync:{mailbox_id}", timeout=SYNC_LOCK_TTL)
    if not await lock.acquire(blocking=False):
        # The sync running now holds the lock and sees the flag before it lets go.
        return
    try:
        # GETDEL clears the flag before each sync, so a push that lands during the sync sets
        # it again and the loop reads the history once more from the new cursor.
        # The budget is checked before GETDEL, so a job out of time leaves the flag set, and
        # the EXISTS check after the release queues a fresh job for it: no push is lost.
        deadline = monotonic() + SYNC_LOOP_BUDGET
        while monotonic() < deadline and await redis.getdel(pending_key):
            try:
                outcome = await sync_mailbox(ctx["services"], mailbox_id)
            except RateLimited as exc:
                # The cursor did not move, so the retry reads the same changes again; the
                # retried job sets the flag again. At least 5 s: a Retry-After of 0 would
                # burn every try at once.
                raise Retry(defer=max(exc.retry_after, 5)) from exc
            for email_id in outcome.email_ids:
                await redis.enqueue_job(PROCESS_EMAIL_JOB, email_id)
            if outcome.has_more:
                # The connector stopped at its per-fetch cap; the cursor moved past this
                # batch. Setting the flag runs the loop again, within the same budget and
                # hand-off as a push, so one long gap never runs into the job timeout.
                await redis.set(pending_key, 1, ex=SYNC_PENDING_TTL)
    finally:
        # A sync that ran past the lock timeout no longer owns the lock (it expired, and
        # another sync may hold it now). Nothing is left to release; failing here would
        # fail a job whose mail is already stored and queued for triage.
        with contextlib.suppress(LockNotOwnedError):
            await lock.release()
    # A push between the last GETDEL and the release found the lock busy and returned, or the
    # loop ran out of budget with the flag still set. Nobody holds the lock to see that flag
    # now, so a fresh job picks it up.
    if await redis.exists(pending_key):
        await redis.enqueue_job(SYNC_MAILBOX_JOB, mailbox_id)


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
        func(process_email_job, name=PROCESS_EMAIL_JOB, max_tries=PROCESS_EMAIL_TRIES),
        # keep_result=0: the job returns nothing worth reading back, so store no result.
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
    job_timeout = SYNC_LOCK_TTL
