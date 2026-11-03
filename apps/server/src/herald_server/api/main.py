from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from herald_server.api.routes import (
    emails,
    events,
    health,
    internal,
    mailboxes,
    oauth,
    providers,
    webhooks,
    workspaces,
)
from herald_server.internal.client import AgentApi
from herald_server.internal.token import internal_token
from herald_server.logs import setup_logging
from herald_server.queue import ArqQueue, InlineQueue, JobQueue
from herald_server.services import Services, build_services
from herald_server.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    # After uvicorn's own logging setup, which runs before it imports the app.
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        services: Services = build_services(settings)
        inline = settings.queue == "inline"
        token = internal_token(settings, allow_random=inline)
        app.state.internal_token = token
        # Triage that runs in this process (the inline queue, and the owner's trial read) calls
        # these same internal routes in memory, so it never opens the database either.
        agent_api = AgentApi.in_process(app, token)
        queue: JobQueue = (
            InlineQueue(services, agent_api)
            if inline
            else await ArqQueue.connect(settings.redis_url)
        )
        app.state.services = services
        app.state.agent_api = agent_api
        app.state.queue = queue
        yield
        await queue.close()
        await agent_api.close()
        await services.bus.close()
        await services.http.aclose()
        services.engine.dispose()
        # Last: the SDK batches spans in a background thread, and a process that exits without
        # this flush loses the final ones.
        services.tracing.shutdown()

    app = FastAPI(title="Herald", debug=settings.debug, lifespan=lifespan)
    for module in (
        health,
        workspaces,
        emails,
        events,
        mailboxes,
        oauth,
        providers,
        webhooks,
        internal,
    ):
        app.include_router(module.router)
    return app


app = create_app()
