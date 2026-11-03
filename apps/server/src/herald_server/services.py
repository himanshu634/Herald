"""Long-lived objects shared by the API and the worker, built once per process."""

from dataclasses import dataclass

import httpx
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, col, create_engine, select

from herald_core.adapters import Notifier
from herald_core.graph import build_graph
from herald_core.model import AnthropicModel, FakeModel, TriageModel
from herald_server.bus import EventBus, InMemoryEventBus, RedisEventBus
from herald_server.connectors import build_connectors
from herald_server.connectors.base import MailConnector
from herald_server.crypto import BadSecret, SecretBox
from herald_server.models import Mailbox
from herald_server.notifier import LogNotifier, NtfyNotifier
from herald_server.settings import Settings


@dataclass
class Services:
    settings: Settings
    engine: Engine
    bus: EventBus
    notifier: Notifier
    graph: CompiledStateGraph
    http: httpx.AsyncClient
    secrets: SecretBox | None  # None when token_key is unset
    connectors: dict[str, MailConnector]


def _check_token_key(engine: Engine, secrets: SecretBox) -> None:
    """Fail startup when the key cannot open stored mailbox credentials.

    A valid but wrong key (say the worker's env differs from the API's) would otherwise
    move every mailbox it syncs to needs_reauth, and each owner would have to reconnect.
    """
    # Cross-tenant by design: one sample row from any workspace tests the process's key.
    with Session(engine) as session:
        sealed = session.exec(
            select(Mailbox.credentials_enc).where(col(Mailbox.credentials_enc).is_not(None))
        ).first()
    if sealed is None:
        return
    try:
        secrets.open(sealed)
    except BadSecret:
        # from None: the message must never carry the key, the token or the sealed value.
        raise RuntimeError("HERALD_TOKEN_KEY cannot decrypt stored mailbox credentials") from None


def build_services(settings: Settings) -> Services:
    connect_args = (
        {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    )
    engine = create_engine(settings.database_url, connect_args=connect_args)
    # Skeleton only: swap for Alembic migrations before the schema settles.
    SQLModel.metadata.create_all(engine)
    secrets = SecretBox(settings.token_key) if settings.token_key else None
    if secrets is not None:
        _check_token_key(engine, secrets)

    bus: EventBus = (
        RedisEventBus(settings.redis_url) if settings.bus == "redis" else InMemoryEventBus()
    )
    notifier: Notifier = (
        NtfyNotifier(settings.ntfy_url, settings.ntfy_topic)
        if settings.ntfy_topic
        else LogNotifier()
    )
    model: TriageModel = (
        AnthropicModel(model=settings.model_name)
        if settings.model_provider == "anthropic"
        else FakeModel()
    )
    http = httpx.AsyncClient(timeout=20)
    return Services(
        settings=settings,
        engine=engine,
        bus=bus,
        notifier=notifier,
        graph=build_graph(model),
        http=http,
        secrets=secrets,
        connectors=build_connectors(settings, http),
    )
