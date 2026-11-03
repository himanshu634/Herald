"""Tests for the startup schema check and debug tracebacks."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlmodel import create_engine

from herald_server.api.main import create_app
from herald_server.services import build_services


def test_startup_names_columns_missing_from_an_old_database(settings):
    # A workspace table from before the demo column: create_all leaves it as it is.
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE workspace (id CHAR(32) PRIMARY KEY, name VARCHAR, config JSON,"
                " setup_done BOOLEAN, created_at DATETIME)"
            )
        )
    engine.dispose()

    with pytest.raises(RuntimeError, match=r"missing: workspace\.demo\."):
        build_services(settings)


async def _boom_response(settings) -> str:
    app = create_app(settings)

    @app.get("/boom")
    def boom() -> None:
        raise ValueError("kaboom")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")
    assert response.status_code == 500
    return response.text


async def test_debug_sends_the_traceback(settings):
    body = await _boom_response(settings.model_copy(update={"debug": True}))
    assert "ValueError: kaboom" in body


async def test_without_debug_the_traceback_stays_on_the_server(settings):
    body = await _boom_response(settings)
    assert body == "Internal Server Error"
