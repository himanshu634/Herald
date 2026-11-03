import httpx
import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session, SQLModel, create_engine

from herald_server.connectors import build_connectors
from herald_server.crypto import SecretBox
from herald_server.models import Mailbox, Workspace
from herald_server.services import build_services
from herald_server.settings import Settings


async def test_no_connectors_without_google_settings():
    async with httpx.AsyncClient() as http:
        settings = Settings(
            token_key=None, google_client_id=None, google_client_secret=None, gmail_topic=None
        )
        assert build_connectors(settings, http) == {}


async def test_services_have_secrets_when_key_set(app):
    assert app.state.services.secrets is not None


def add_sealed_mailbox(settings: Settings, secrets: SecretBox) -> None:
    engine = create_engine(settings.database_url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        workspace = Workspace(name="Shop", config={})
        session.add(workspace)
        session.flush()
        session.add(
            Mailbox(
                workspace_id=workspace.id,
                provider="gmail",
                email_address="owner@shop.in",
                credentials_enc=secrets.seal({"refresh_token": "r1"}),
            )
        )
        session.commit()
    engine.dispose()


async def test_startup_succeeds_with_no_mailboxes(settings):
    services = build_services(settings)
    assert services.secrets is not None
    await services.http.aclose()
    services.engine.dispose()


async def test_startup_succeeds_when_key_opens_stored_credentials(settings):
    assert settings.token_key is not None
    add_sealed_mailbox(settings, SecretBox(settings.token_key))

    services = build_services(settings)
    await services.http.aclose()
    services.engine.dispose()


def test_startup_fails_when_key_cannot_open_stored_credentials(settings):
    # A valid but different key (e.g. the worker's env differs from the API's) would
    # otherwise move every mailbox to needs_reauth on its next sync.
    add_sealed_mailbox(settings, SecretBox(Fernet.generate_key().decode()))

    with pytest.raises(RuntimeError) as raised:
        build_services(settings)

    assert str(raised.value) == "HERALD_TOKEN_KEY cannot decrypt stored mailbox credentials"
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__
