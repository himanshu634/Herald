"""Long-lived objects shared by the API and the worker, built once per process."""

from dataclasses import dataclass

from anthropic import AsyncAnthropic
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import Engine
from sqlmodel import SQLModel, create_engine

from herald_core.adapters import Notifier
from herald_core.graph import build_graph
from herald_core.model import AnthropicModel, FakeModel, TriageModel
from herald_server.bus import EventBus, InMemoryEventBus, RedisEventBus
from herald_server.notifier import LogNotifier, NtfyNotifier
from herald_server.settings import Settings


@dataclass
class Services:
    settings: Settings
    engine: Engine
    bus: EventBus
    notifier: Notifier
    graph: CompiledStateGraph


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
    return Services(
        settings=settings,
        engine=engine,
        bus=bus,
        notifier=notifier,
        graph=build_graph(build_model(settings)),
    )


def build_model(settings: Settings) -> TriageModel:
    if settings.model_provider == "fake":
        return FakeModel()
    key = settings.anthropic_api_key
    # No key in settings: the SDK falls back to its own credential lookup.
    client = AsyncAnthropic(api_key=key.get_secret_value()) if key else None
    return AnthropicModel(client=client, model=settings.model_name)
