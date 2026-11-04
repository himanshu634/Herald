import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fake_connector import FakeConnector
from httpx import ASGITransport, AsyncClient

from herald_server.api.main import create_app
from herald_server.internal.client import AgentApi
from herald_server.migrate import upgrade
from herald_server.settings import Settings


@pytest.fixture(scope="session")
def migrated_db(tmp_path_factory) -> Path:
    # Startup refuses a database that is not at the latest revision. Migrate one file per run
    # and copy it into each test, instead of running every migration for every test.
    path = tmp_path_factory.mktemp("migrated") / "herald.db"
    upgrade(f"sqlite:///{path}")
    return path


@pytest.fixture
def settings(tmp_path, migrated_db) -> Settings:
    # One process, no Redis or Postgres: SQLite file, in-memory bus, inline queue, fake model.
    db = tmp_path / "herald.db"
    shutil.copy(migrated_db, db)
    return Settings(
        database_url=f"sqlite:///{db}",
        bus="memory",
        queue="inline",
        model_provider="fake",
        token_key=Fernet.generate_key().decode(),
        # Set here so a token in .env or the shell cannot leak into the tests.
        internal_token=None,
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


@pytest.fixture
def fake_connector(app) -> FakeConnector:
    connector = FakeConnector()
    app.state.services.connectors["fake"] = connector
    return connector


@pytest.fixture
async def agent_api(app) -> AsyncIterator[AgentApi]:
    # The worker's client, calling the internal routes in memory.
    api = AgentApi.in_process(app, app.state.internal_token)
    yield api
    await api.close()
