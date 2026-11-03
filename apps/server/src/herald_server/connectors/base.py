"""The contract every mail provider implements, and the types that cross it."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel


class InboundMessage(BaseModel):
    provider_message_id: str
    sender: str  # bare address, lower-case
    subject: str
    body: str  # plain text, at most 50_000 chars
    received_at: datetime
    thread_id: str | None = None  # the provider's conversation id, if it has one
    # RFC 5322 headers a reply needs. None when the mail has none.
    internet_message_id: str | None = None  # Message-ID, with its angle brackets
    references: str | None = None  # space-separated ids, newest last
    reply_to: str | None = None  # one bare lower-case address


class FetchResult(BaseModel):
    messages: list[InboundMessage]
    cursor: str  # where the next fetch starts
    # True when the connector stopped early (a per-fetch cap) and more changes are waiting
    # after `cursor`. The caller fetches again; one huge fetch could outlast the job timeout.
    has_more: bool = False


class ConnectedAccount(BaseModel):
    email_address: str  # lower-case
    credentials: dict[str, str]
    can_send: bool = False  # the owner granted permission to send mail


class Subscription(BaseModel):
    expires_at: datetime | None
    provider_state: dict[str, Any]


class PushNotice(BaseModel):
    email_address: str  # lower-case


class AuthRevoked(Exception):
    """The owner revoked access, or the password changed."""


class MissingRefreshToken(Exception):
    """OAuth returned no long-lived credential."""


class RateLimited(Exception):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


class PushRejected(Exception):
    """Bad or missing signature: answer 401."""


class PushIgnored(Exception):
    """Well-signed but unusable body: acknowledge with 204."""


class MailConnector(Protocol):
    """One mail provider (Gmail first; Outlook and IMAP later).

    `fetch_changes(cursor=None)` means "first sync": recent mail plus a fresh cursor.
    A connector that finds its cursor too old falls back to that same path itself,
    and never raises for an expired cursor. A provider without push raises
    `PushIgnored` from `parse_push`.
    """

    provider: str

    def authorization_url(self, state: str) -> str: ...

    async def complete_authorization(self, code: str) -> ConnectedAccount: ...

    async def subscribe(
        self, credentials: dict[str, str], provider_state: dict[str, Any]
    ) -> Subscription: ...

    async def unsubscribe(
        self, credentials: dict[str, str], provider_state: dict[str, Any]
    ) -> None: ...

    async def fetch_changes(
        self, credentials: dict[str, str], cursor: str | None
    ) -> FetchResult: ...

    async def revoke(self, credentials: dict[str, str]) -> None: ...

    async def parse_push(self, headers: Mapping[str, str], body: bytes) -> PushNotice: ...
