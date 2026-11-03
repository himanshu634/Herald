from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from herald_server.api.main import create_app
from herald_server.settings import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    # One process, no Redis or Postgres: SQLite file, in-memory bus, inline queue, fake model.
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'herald.db'}",
        bus="memory",
        queue="inline",
        model_provider="fake",
        ntfy_topic=None,
    )


@pytest.fixture
async def app(settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
