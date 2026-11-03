"""A scripted MailConnector for tests: no network."""

import json
from collections.abc import Mapping
from typing import Any

from herald_server.connectors.base import (
    ConnectedAccount,
    FetchResult,
    InboundMessage,
    PushIgnored,
    PushNotice,
    PushRejected,
    Subscription,
)


class FakeConnector:
    provider = "fake"

    def __init__(self) -> None:
        self.queue: list[InboundMessage] = []
        # When set, each fetch returns the next batch, with has_more while batches remain.
        self.batches: list[list[InboundMessage]] = []
        self.raise_on_fetch: Exception | None = None
        self.raise_on_authorize: Exception | None = None
        self.raise_on_subscribe: Exception | None = None
        self.subscription = Subscription(expires_at=None, provider_state={})
        self.calls: list[str] = []
        self.account = ConnectedAccount(email_address="owner@shop.in", credentials={"token": "t"})

    def authorization_url(self, state: str) -> str:
        self.calls.append("authorization_url")
        return f"https://fake.example/auth?state={state}"

    async def complete_authorization(self, code: str) -> ConnectedAccount:
        self.calls.append("complete_authorization")
        if self.raise_on_authorize is not None:
            raise self.raise_on_authorize
        return self.account

    async def subscribe(
        self, credentials: dict[str, str], provider_state: dict[str, Any]
    ) -> Subscription:
        self.calls.append("subscribe")
        if self.raise_on_subscribe is not None:
            raise self.raise_on_subscribe
        return self.subscription

    async def unsubscribe(
        self, credentials: dict[str, str], provider_state: dict[str, Any]
    ) -> None:
        self.calls.append("unsubscribe")

    async def fetch_changes(self, credentials: dict[str, str], cursor: str | None) -> FetchResult:
        self.calls.append("fetch_changes")
        if self.raise_on_fetch is not None:
            raise self.raise_on_fetch
        next_cursor = str(int(cursor or 0) + 1)
        if self.batches:
            batch = self.batches.pop(0)
            return FetchResult(messages=batch, cursor=next_cursor, has_more=bool(self.batches))
        messages, self.queue = self.queue, []
        return FetchResult(messages=messages, cursor=next_cursor)

    async def revoke(self, credentials: dict[str, str]) -> None:
        self.calls.append("revoke")

    async def parse_push(self, headers: Mapping[str, str], body: bytes) -> PushNotice:
        self.calls.append("parse_push")
        if headers.get("x-fake-auth") != "ok":
            raise PushRejected("bad signature")
        try:
            return PushNotice(email_address=json.loads(body)["email"].lower())
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise PushIgnored("unusable body") from exc
