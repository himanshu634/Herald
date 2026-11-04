"""Tests for startup checks and debug tracebacks."""

from httpx import ASGITransport, AsyncClient

from herald_server.api.main import create_app
from scripted_model import ScriptedModel


async def _boom_response(settings) -> str:
    app = create_app(settings, ScriptedModel())

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
