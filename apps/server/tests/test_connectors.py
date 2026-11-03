import httpx

from herald_server.connectors import build_connectors
from herald_server.settings import Settings


async def test_no_connectors_without_google_settings():
    async with httpx.AsyncClient() as http:
        assert build_connectors(Settings(), http) == {}


async def test_services_have_secrets_when_key_set(app):
    assert app.state.services.secrets is not None
