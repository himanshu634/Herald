"""Mail connectors: the provider-neutral registry."""

import httpx

from herald_server.connectors.base import MailConnector
from herald_server.settings import Settings


def build_connectors(settings: Settings, http: httpx.AsyncClient) -> dict[str, MailConnector]:
    """Providers that are configured, by name. Empty until a provider is added."""
    return {}
