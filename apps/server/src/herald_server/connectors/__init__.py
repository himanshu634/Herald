"""Mail connectors: the provider-neutral registry."""

import httpx

from herald_server.connectors.base import MailConnector
from herald_server.connectors.gmail.client import GmailClient
from herald_server.connectors.gmail.connector import GmailConnector
from herald_server.settings import Settings


def build_connectors(settings: Settings, http: httpx.AsyncClient) -> dict[str, MailConnector]:
    """Providers that are configured, by name."""
    connectors: dict[str, MailConnector] = {}
    # Gmail needs the OAuth client, the Pub/Sub topic for watch, and token_key to encrypt the
    # refresh token it hands back. Push verification settings are optional: without them
    # pushes are rejected and polling still syncs.
    if (
        settings.token_key
        and settings.google_client_id
        and settings.google_client_secret
        and settings.gmail_topic
    ):
        client = GmailClient(
            http,
            settings.google_client_id,
            settings.google_client_secret,
            f"{settings.public_api_url}/api/oauth/gmail/callback",
        )
        connectors["gmail"] = GmailConnector(
            client,
            client_id=settings.google_client_id,
            topic=settings.gmail_topic,
            push_audience=settings.gmail_push_audience,
            push_service_account=settings.gmail_push_service_account,
        )
    return connectors
