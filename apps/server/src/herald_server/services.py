"""Long-lived objects shared by the API and the worker, built once per process."""

from dataclasses import dataclass

import httpx
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import Engine, inspect
from sqlmodel import Session, SQLModel, col, create_engine, select

from herald_core.graph import build_graph
from herald_core.model import AnthropicModel, FakeModel, TriageModel
from herald_server.bus import EventBus, InMemoryEventBus, RedisEventBus
from herald_server.connectors import build_connectors
from herald_server.connectors.base import MailConnector
from herald_server.crypto import BadSecret, SecretBox
from herald_server.models import Mailbox, MailboxStatus
from herald_server.settings import Settings
from herald_server.tracing import Tracing, build_tracing


@dataclass
class Services:
    settings: Settings
    engine: Engine
    bus: EventBus
    model: TriageModel
    graph: CompiledStateGraph
    http: httpx.AsyncClient
    secrets: SecretBox | None  # None when token_key is unset
    connectors: dict[str, MailConnector]
    tracing: Tracing


def _check_schema(engine: Engine) -> None:
    """Fail startup when the database is missing a column the models expect.

    create_all only creates missing tables. It never adds a column to a table that already
    exists, so a database made before a model change would fail every query on that table
    with a bare 500. There are no migrations yet, so the fix is to recreate the database.
    """
    inspector = inspect(engine)
    missing = []
    for table in SQLModel.metadata.sorted_tables:
        have = {column["name"] for column in inspector.get_columns(table.name)}
        missing += [f"{table.name}.{c.name}" for c in table.columns if c.name not in have]
    if missing:
        raise RuntimeError(
            f"Database schema is out of date, missing: {', '.join(missing)}. "
            "There are no migrations yet: delete apps/server/herald-dev.db (lite mode), "
            "or reset Postgres with docker compose -f infra/docker-compose.yml down -v "
            "(this deletes its data)."
        )


def _check_token_key(engine: Engine, secrets: SecretBox) -> None:
    """Fail startup when the key cannot open stored mailbox credentials.

    A valid but wrong key (say the worker's env differs from the API's) would otherwise
    move every mailbox it syncs to needs_reauth, and each owner would have to reconnect.
    """
    # Cross-tenant by design: one sample row from any workspace tests the process's key.
    # Prefer an ACTIVE mailbox: those are the ones syncs open. A needs_reauth row may hold
    # credentials sealed with an older key (that can be why it needs a reconnect), and it must
    # not block startup while the active mailboxes open fine. Any row is the fallback.
    has_credentials = col(Mailbox.credentials_enc).is_not(None)
    with Session(engine) as session:
        sealed = session.exec(
            select(Mailbox.credentials_enc).where(
                has_credentials, Mailbox.status == MailboxStatus.ACTIVE
            )
        ).first()
        if sealed is None:
            sealed = session.exec(select(Mailbox.credentials_enc).where(has_credentials)).first()
    if sealed is None:
        return
    try:
        secrets.open(sealed)
    except BadSecret:
        # from None: the message must never carry the key, the token or the sealed value.
        raise RuntimeError("HERALD_TOKEN_KEY cannot decrypt stored mailbox credentials") from None


def _anthropic_key(settings: Settings) -> str:
    # Without a key every email fails in the model call, so stop here instead.
    if settings.anthropic_api_key is None or not settings.anthropic_api_key.get_secret_value():
        raise RuntimeError("HERALD_MODEL_PROVIDER is anthropic but ANTHROPIC_API_KEY is not set")
    return settings.anthropic_api_key.get_secret_value()


def build_services(settings: Settings) -> Services:
    connect_args = (
        {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    )
    engine = create_engine(settings.database_url, connect_args=connect_args)
    # Skeleton only: swap for Alembic migrations before the schema settles.
    SQLModel.metadata.create_all(engine)
    _check_schema(engine)
    secrets = SecretBox(settings.token_key) if settings.token_key else None
    if secrets is not None:
        _check_token_key(engine, secrets)

    bus: EventBus = (
        RedisEventBus(settings.redis_url) if settings.bus == "redis" else InMemoryEventBus()
    )
    model: TriageModel = (
        AnthropicModel(model=settings.model_name, api_key=_anthropic_key(settings))
        if settings.model_provider == "anthropic"
        else FakeModel()
    )
    tracing = build_tracing(settings)
    model = tracing.wrap_model(model)
    http = httpx.AsyncClient(timeout=20)
    return Services(
        settings=settings,
        engine=engine,
        bus=bus,
        model=model,
        graph=build_graph(model),
        http=http,
        secrets=secrets,
        connectors=build_connectors(settings, http),
        tracing=tracing,
    )
