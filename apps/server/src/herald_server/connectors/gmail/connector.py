"""Gmail as a MailConnector: OAuth consent, Pub/Sub watch, and history sync with a backfill."""

import logging
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlencode

from herald_server.connectors.base import (
    ConnectedAccount,
    FetchResult,
    InboundMessage,
    MailConnector,
    MissingRefreshToken,
    PushNotice,
    PushRejected,
    Subscription,
)
from herald_server.connectors.gmail.client import (
    AUTH_URL,
    SCOPE,
    GmailClient,
    HistoryExpired,
    MessageGone,
)
from herald_server.connectors.gmail.mime import parse_raw_message

log = logging.getLogger(__name__)

BACKFILL_QUERY = "in:inbox newer_than:2d"
BACKFILL_LIMIT = 50


class GmailConnector(MailConnector):
    provider = "gmail"

    def __init__(
        self,
        client: GmailClient,
        *,
        client_id: str,
        topic: str,
        push_audience: str | None,
        push_service_account: str | None,
        signing_key_for: Callable[[str], Any] | None = None,
    ) -> None:
        self._client = client
        self._client_id = client_id
        self._topic = topic
        # Used by parse_push (Task 7) to verify Pub/Sub push tokens.
        self._push_audience = push_audience
        self._push_service_account = push_service_account
        self._signing_key_for = signing_key_for

    def authorization_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._client.redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            # offline + consent: Google returns a refresh token on every connect,
            # including a reconnect of an account that granted access before.
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    async def complete_authorization(self, code: str) -> ConnectedAccount:
        tokens = await self._client.exchange_code(code)
        if tokens.refresh_token is None:
            raise MissingRefreshToken("Google returned no refresh token")
        profile = await self._client.get_profile(tokens.access_token)
        return ConnectedAccount(
            email_address=profile.email_address.lower(),
            credentials={"refresh_token": tokens.refresh_token},
        )

    async def subscribe(
        self, credentials: dict[str, str], provider_state: dict[str, Any]
    ) -> Subscription:
        access = await self._client.refresh(credentials["refresh_token"])
        watch = await self._client.watch(access, self._topic)
        return Subscription(expires_at=watch.expiration, provider_state={})

    async def unsubscribe(
        self, credentials: dict[str, str], provider_state: dict[str, Any]
    ) -> None:
        access = await self._client.refresh(credentials["refresh_token"])
        await self._client.stop(access)

    async def revoke(self, credentials: dict[str, str]) -> None:
        await self._client.revoke(credentials["refresh_token"])

    async def fetch_changes(self, credentials: dict[str, str], cursor: str | None) -> FetchResult:
        access = await self._client.refresh(credentials["refresh_token"])
        if cursor is None:
            ids, new_cursor = await self._backfill(access)
        else:
            try:
                ids, new_cursor = await self._history(access, cursor)
            except HistoryExpired:
                # Gmail keeps about a week of history. Any ids gathered from earlier pages are
                # dropped: the backfill below covers the recent inbox and gives a fresh cursor.
                log.info("gmail history cursor expired; backfilling")
                ids, new_cursor = await self._backfill(access)

        messages: list[InboundMessage] = []
        for message_id in ids:
            try:
                raw = await self._client.get_raw_message(access, message_id)
            except MessageGone:
                continue  # deleted between the listing and now
            if "INBOX" not in raw.label_ids:
                continue  # archived, or moved out of the inbox, since it was listed
            try:
                parsed = parse_raw_message(raw.raw)
            except Exception as exc:
                # One malformed email must not stall the mailbox: if it raised here every sync
                # would fail at the same message and the cursor would never move. Log the id and
                # error type only, never content.
                log.warning(
                    "skipping unparseable gmail message %s (%s)", raw.id, type(exc).__name__
                )
                continue
            messages.append(
                InboundMessage(
                    provider_message_id=raw.id,
                    sender=parsed.sender,
                    subject=parsed.subject,
                    body=parsed.body,
                    received_at=raw.internal_date,
                )
            )
        return FetchResult(messages=messages, cursor=new_cursor)

    async def _backfill(self, access: str) -> tuple[list[str], str]:
        """Recent inbox mail and a fresh cursor, for a first sync or an expired cursor."""
        # Read the profile's historyId before listing: mail that lands while we list and fetch
        # is then after the cursor, so the next history sync picks it up. Reading it after the
        # list would put that mail before the cursor and lose it. Mail caught by both the list
        # and the next sync is removed by dedupe on provider_message_id.
        profile = await self._client.get_profile(access)
        page = await self._client.list_messages(access, BACKFILL_QUERY, BACKFILL_LIMIT)
        return page.message_ids, profile.history_id

    async def _history(self, access: str, cursor: str) -> tuple[list[str], str]:
        """Inbox message ids added since the cursor, across every page, and the next cursor."""
        ids: dict[str, None] = {}  # insertion-ordered set: a message can show up on two pages
        page_token: str | None = None
        while True:
            page = await self._client.list_history(access, cursor, page_token)
            ids.update(dict.fromkeys(page.message_ids))
            if page.next_page_token is None:
                break
            page_token = page.next_page_token
        # The cursor is the last page's historyId. Each page reports the mailbox's current
        # historyId when it was served, so the last page's is the newest, and we only reach it
        # after every page is read. An earlier page's id is older, so the next sync would read
        # again what these pages already returned (dedupe absorbs that, but it is wasted work).
        return list(ids), page.history_id

    async def parse_push(self, headers: Mapping[str, str], body: bytes) -> PushNotice:
        # Task 7 replaces this with Pub/Sub token verification. Until then every push is
        # rejected, so nothing unsigned is ever accepted.
        raise PushRejected("push not configured")
