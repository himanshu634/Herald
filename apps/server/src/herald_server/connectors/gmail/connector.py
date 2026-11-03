"""Gmail as a MailConnector: OAuth consent, Pub/Sub watch, and history sync with a backfill."""

import logging
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlencode

from asyncer import asyncify

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
    MessageUnavailable,
    is_inbox_mail,
)
from herald_server.connectors.gmail.mime import parse_raw_message
from herald_server.connectors.gmail.push import (
    decode_envelope,
    google_signing_key,
    verify_push_token,
)

log = logging.getLogger(__name__)

BACKFILL_QUERY = "in:inbox newer_than:2d"
BACKFILL_LIMIT = 50
# Messages downloaded by one fetch at most. A long gap (a reconnect or resume keeps the
# cursor) could hold thousands: one fetch for all of them would outlast the job timeout,
# get cancelled before it stores anything, and never move the cursor. Capped, each fetch
# stores its batch and moves the cursor, and `has_more` asks the caller for the next one.
MAX_MESSAGES_PER_FETCH = 100


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
        # Used by parse_push to verify Pub/Sub push tokens.
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
        has_more = False  # the backfill is at most BACKFILL_LIMIT, under the cap
        if cursor is None:
            ids, new_cursor = await self._backfill(access)
        else:
            try:
                ids, new_cursor, has_more = await self._history(access, cursor)
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
            except MessageUnavailable as exc:
                # A permanent refusal for this one message (400 or 410): raising would fail
                # every sync at it and the cursor would never move. Any other refusal raises
                # from the client and fails the fetch. Log the id and error type only.
                log.warning(
                    "skipping unavailable gmail message %s (%s)", message_id, type(exc).__name__
                )
                continue
            if not is_inbox_mail(raw.label_ids):
                # Archived since it was listed, or the owner's own mail: the backfill query
                # in:inbox also matches mail the owner sent to themselves.
                continue
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
                    thread_id=raw.thread_id,
                )
            )
        return FetchResult(messages=messages, cursor=new_cursor, has_more=has_more)

    async def _backfill(self, access: str) -> tuple[list[str], str]:
        """Recent inbox mail and a fresh cursor, for a first sync or an expired cursor."""
        # Read the profile's historyId before listing: mail that lands while we list and fetch
        # is then after the cursor, so the next history sync picks it up. Reading it after the
        # list would put that mail before the cursor and lose it. Mail caught by both the list
        # and the next sync is removed by dedupe on provider_message_id.
        profile = await self._client.get_profile(access)
        page = await self._client.list_messages(access, BACKFILL_QUERY, BACKFILL_LIMIT)
        return page.message_ids, profile.history_id

    async def _history(self, access: str, cursor: str) -> tuple[list[str], str, bool]:
        """Inbox message ids added since the cursor, the next cursor, and whether more wait.

        Takes whole history records, in order, until MAX_MESSAGES_PER_FETCH would be passed.
        """
        ids: dict[str, None] = {}  # insertion-ordered set: a message can show up on two pages
        page = await self._client.list_history(access, cursor)
        # When every page is read, the cursor is the FIRST page's historyId. Every history
        # record up to it is enumerated by the pages, so this is loss-safe whether Gmail pages
        # a snapshot or a live list. Records added mid-paging are simply re-read on the next
        # sync, and dedupe absorbs them. The last page's id would be newer: if paging is a
        # snapshot, records added mid-paging would sit before that cursor without being
        # returned, and be skipped forever.
        first_page_history_id = page.history_id
        start = int(cursor)
        last_taken: str | None = None
        while True:
            for record in page.records:
                # Gmail documents records AFTER startHistoryId, but do not bet the mailbox on
                # it: if the start record came back, a batch that ends on a big record would
                # return that same record as its cursor, and every fetch would read it again
                # forever. Skipping it is loss-free: the batch that ended on it took its mail.
                # Ids are integers, so compare them as such ("999" > "1000" as strings).
                if int(record.id) <= start:
                    continue
                new = [i for i in record.message_ids if i not in ids]
                # Stop before a record that would pass the cap, never inside one: the cursor
                # can only name a whole record, and the last record taken is a loss-free start
                # for the next fetch. The first record is taken whole, however big: stopping
                # before it would return the start cursor with has_more and loop on it forever.
                # With the skip above, a cursor returned with has_more is always past the start.
                if last_taken is not None and len(ids) + len(new) > MAX_MESSAGES_PER_FETCH:
                    return list(ids), last_taken, True
                ids.update(dict.fromkeys(new))
                last_taken = record.id
            if page.next_page_token is None:
                break
            page = await self._client.list_history(access, cursor, page.next_page_token)
        return list(ids), first_page_history_id, False

    async def parse_push(self, headers: Mapping[str, str], body: bytes) -> PushNotice:
        # Without both settings there is nothing to verify against. Reject instead of
        # accepting: an unsigned push must never be trusted.
        if not self._push_audience or not self._push_service_account:
            raise PushRejected("push verification is not configured")
        # Plain dicts are case-sensitive, Starlette Headers are not: lower-case to cover both.
        lowered = {k.lower(): v for k, v in headers.items()}
        scheme, _, token = lowered.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise PushRejected("missing bearer token")
        # The default key lookup does blocking HTTP, so verify in a worker thread.
        await asyncify(verify_push_token)(
            token.strip(),
            audience=self._push_audience,
            service_account=self._push_service_account,
            signing_key_for=self._signing_key_for or google_signing_key,
        )
        return decode_envelope(body)
