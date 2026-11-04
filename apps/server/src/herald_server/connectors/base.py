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
    in_spam: bool = False  # the provider filed it as spam


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


class OutboundReply(BaseModel):
    from_address: str
    to_address: str
    subject: str  # final subject, "Re: ..." already applied by the caller
    body: str  # plain text
    in_reply_to: str | None  # the customer email's Message-ID
    references: str | None  # its References plus its Message-ID
    provider_thread_id: str | None


class SentReply(BaseModel):
    provider_message_id: str


class AuthRevoked(Exception):
    """The owner revoked access, or the password changed."""


class MissingRefreshToken(Exception):
    """OAuth returned no long-lived credential."""


class RateLimited(Exception):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


class SendNotAllowed(Exception):
    """The account did not grant permission to send."""


class SendRejected(Exception):
    """The provider refused this message. It was not sent."""


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

    Mail is read from the inbox, and from the Spam folder too when `include_spam` is true.
    Mail that moves into the inbox later (marked "not spam", or moved back) counts as new.
    """

    provider: str

    def authorization_url(self, state: str) -> str: ...

    async def complete_authorization(self, code: str) -> ConnectedAccount: ...

    async def subscribe(
        self,
        credentials: dict[str, str],
        provider_state: dict[str, Any],
        *,
        include_spam: bool = False,
    ) -> Subscription: ...

    async def unsubscribe(
        self, credentials: dict[str, str], provider_state: dict[str, Any]
    ) -> None: ...

    async def fetch_changes(
        self, credentials: dict[str, str], cursor: str | None, *, include_spam: bool = False
    ) -> FetchResult: ...

    async def fetch_recent_spam(self, credentials: dict[str, str]) -> list[InboundMessage]:
        """Recent mail in the Spam folder, for when the owner turns Spam on. Moves no cursor."""
        ...

    async def revoke(self, credentials: dict[str, str]) -> None: ...

    async def parse_push(self, headers: Mapping[str, str], body: bytes) -> PushNotice: ...

    async def send_reply(self, credentials: dict[str, str], reply: OutboundReply) -> SentReply:
        """Send one reply as the owner.

        `AuthRevoked`, `RateLimited`, `SendNotAllowed` and `SendRejected` all mean the message
        was not sent. Any other exception (a timeout, a 5xx) means the outcome is unknown:
        the customer may have got the email. The caller never retries a send.
        """
        ...
