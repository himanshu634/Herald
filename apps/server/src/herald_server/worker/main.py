"""arq worker that runs the triage pipeline.

Run: uv run arq herald_server.worker.main.WorkerSettings
"""

from typing import Any

from arq.connections import RedisSettings
from arq.worker import func

from herald_server.pipeline import process_email
from herald_server.queue import PROCESS_EMAIL_JOB
from herald_server.services import build_services
from herald_server.settings import get_settings

settings = get_settings()


async def startup(ctx: dict[str, Any]) -> None:
    ctx["services"] = build_services(settings)


async def shutdown(ctx: dict[str, Any]) -> None:
    services = ctx["services"]
    await services.bus.close()
    services.engine.dispose()


async def process_email_job(ctx: dict[str, Any], email_id: str) -> str:
    decision = await process_email(ctx["services"], email_id)
    return decision.route


class WorkerSettings:
    functions = [func(process_email_job, name=PROCESS_EMAIL_JOB)]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 20
