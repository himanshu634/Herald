"""Long-lived objects shared by the API and the worker, built once per process."""

from dataclasses import dataclass

import httpx
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import Engine
from sqlmodel import SQLModel, create_engine

from herald_core.adapters import Notifier
from herald_core.graph import build_graph
from herald_core.model import AnthropicModel, FakeModel, TriageModel
from herald_server.bus import EventBus, InMemoryEventBus, RedisEventBus
from herald_server.connectors import build_connectors
from herald_server.connectors.base import MailConnector
from herald_server.crypto import SecretBox
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


def build_services(settings: Settings) -> Services:
    connect_args = (
        {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    )
    engine = create_engine(settings.database_url, connect_args=connect_args)
    # Skeleton only: swap for Alembic migrations before the schema settles.
    SQLModel.metadata.create_all(engine)

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
        secrets=SecretBox(settings.token_key) if settings.token_key else None,
        connectors=build_connectors(settings, http),
    )
