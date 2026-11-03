from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from herald_server.api.routes import emails, events, health, workspaces
from herald_server.queue import ArqQueue, InlineQueue, JobQueue
from herald_server.services import Services, build_services
from herald_server.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        services: Services = build_services(settings)
        queue: JobQueue = (
            await ArqQueue.connect(settings.redis_url)
            if settings.queue == "arq"
            else InlineQueue(services)
        )
        app.state.services = services
        app.state.queue = queue
        yield
        await queue.close()
        await services.bus.close()
        services.engine.dispose()

    app = FastAPI(title="Herald", lifespan=lifespan)
    for module in (health, workspaces, emails, events):
        app.include_router(module.router)
    return app


app = create_app()
