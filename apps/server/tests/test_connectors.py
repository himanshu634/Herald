import httpx

from herald_server.connectors import build_connectors
from herald_server.settings import Settings


async def test_no_connectors_without_google_settings():
    async with httpx.AsyncClient() as http:
        settings = Settings(
            token_key=None, google_client_id=None, google_client_secret=None, gmail_topic=None
        )
        assert build_connectors(settings, http) == {}


async def test_services_have_secrets_when_key_set(app):
    assert app.state.services.secrets is not None
