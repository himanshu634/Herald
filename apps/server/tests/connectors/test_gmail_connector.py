"""Tests for GmailConnector: OAuth, history sync, pagination and backfill."""

import base64
import email
import email.policy
import json
import logging
from collections.abc import AsyncIterator
from email.message import EmailMessage
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from herald_server.connectors import build_connectors
from herald_server.connectors.base import MissingRefreshToken, OutboundReply
from herald_server.connectors.gmail.client import (
    API,
    READ_SCOPE,
    SEND_SCOPE,
    TOKEN_URL,
    GmailClient,
)
from herald_server.connectors.gmail.connector import (
    BACKFILL_LIMIT,
    BACKFILL_QUERY,
    BACKFILL_WITH_SPAM_QUERY,
    MAX_MESSAGES_PER_FETCH,
    SPAM_BACKFILL_QUERY,
    GmailConnector,
)
from herald_server.settings import Settings

PROFILE = urlsplit(f"{API}/profile").path
WATCH = urlsplit(f"{API}/watch").path
HISTORY = urlsplit(f"{API}/history").path
MESSAGES = urlsplit(f"{API}/messages").path
TOKEN = urlsplit(TOKEN_URL).path


def _raw(sender: str = "a@b.com", subject: str = "Hi", body: str = "Hello") -> str:
    msg = EmailMessage()
    msg["From"] = sender
    msg["Subject"] = subject
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


class FakeGoogle:
    """One MockTransport handler that routes on URL path and records request order."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.refresh_token: str | None = "r1"
        # The `scope` field of the token response; None leaves it out.
        self.granted_scope: str | None = f"{READ_SCOPE} {SEND_SCOPE}"
        self.email = "owner@shop.in"
        self.profile_history_id = "500"
        self.history_pages: dict[str | None, dict] = {}
        # When set, history is served from these (record id, message ids) like Gmail does:
        # only records after startHistoryId, HISTORY_PAGE_SIZE records per page.
        self.history_records: list[tuple[int, list[str]]] | None = None
        self.history_id_now = "5000"
        # When set, history also lists the record equal to startHistoryId (Gmail documents
        # "after", but the connector must not rely on it).
        self.history_start_inclusive = False
        # Page tokens (None is the first page) whose history request answers 404.
        self.expired_pages: set[str | None] = set()
        self.listed_ids: list[str] = []
        self.watch_labels: list[str] | None = None
        # id -> (raw, labelIds); a missing id answers 404.
        self.messages: dict[str, tuple[str, list[str]]] = {}
        # id -> HTTP status the message get answers with instead.
        self.message_errors: dict[str, int] = {}

    def add_message(self, message_id: str, labels: tuple[str, ...] = ("INBOX",), **kw) -> None:
        self.messages[message_id] = (_raw(**kw), list(labels))

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = request.url.params
        if path == TOKEN:
            self.calls.append("token")
            tokens = {"access_token": "acc"}
            if self.refresh_token is not None:
                tokens["refresh_token"] = self.refresh_token
            if self.granted_scope is not None:
                tokens["scope"] = self.granted_scope
            return httpx.Response(200, json=tokens)
        if path == PROFILE:
            self.calls.append("profile")
            return httpx.Response(
                200, json={"emailAddress": self.email, "historyId": self.profile_history_id}
            )
        if path == WATCH:
            self.calls.append("watch")
            self.watch_labels = json.loads(request.read())["labelIds"]
            return httpx.Response(200, json={"historyId": "9", "expiration": "2000"})
        if path == HISTORY:
            page_token = params.get("pageToken")
            start = params["startHistoryId"]
            self.calls.append(f"history:{start}:{page_token}")
            if page_token in self.expired_pages:
                return httpx.Response(404, json={"error": {"code": 404}})
            if self.history_records is not None:
                return httpx.Response(200, json=self._records_page(int(start), page_token))
            return httpx.Response(200, json=self.history_pages[page_token])
        # Match the list path exactly before treating the path as /messages/{id}.
        if path == MESSAGES:
            self.calls.append(f"list:{params['q']}")
            assert params["maxResults"] == str(BACKFILL_LIMIT)
            return httpx.Response(200, json={"messages": [{"id": i} for i in self.listed_ids]})
        if path.startswith(MESSAGES + "/"):
            message_id = path.rsplit("/", 1)[1]
            self.calls.append(f"get:{message_id}")
            if message_id in self.message_errors:
                return httpx.Response(
                    self.message_errors[message_id], json={"error": {"message": "leak-me-xyz"}}
                )
            if message_id not in self.messages:
                return httpx.Response(404, json={"error": {"code": 404}})
            raw, labels = self.messages[message_id]
            return httpx.Response(
                200,
                json={
                    "id": message_id,
                    "threadId": f"t-{message_id}",
                    "raw": raw,
                    "labelIds": labels,
                    "internalDate": "1000",
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    def _records_page(self, start: int, page_token: str | None) -> dict:
        assert self.history_records is not None
        inclusive = self.history_start_inclusive
        after = [r for r in self.history_records if r[0] > start or (inclusive and r[0] == start)]
        offset = int(page_token or 0)
        chunk = after[offset : offset + HISTORY_PAGE_SIZE]
        page: dict = {
            "historyId": self.history_id_now,
            "history": [
                {
                    "id": str(record_id),
                    "messagesAdded": [
                        {"message": {"id": i, "labelIds": ["INBOX"]}} for i in message_ids
                    ],
                }
                for record_id, message_ids in chunk
            ],
        }
        if offset + HISTORY_PAGE_SIZE < len(after):
            page["nextPageToken"] = str(offset + HISTORY_PAGE_SIZE)
        return page


HISTORY_PAGE_SIZE = 40


def _history_page(history_id: str, ids: list[str], next_page: str | None = None) -> dict:
    # One record per message, with ids counting up to the page's historyId.
    first = int(history_id) - len(ids) + 1
    page: dict = {
        "historyId": history_id,
        "history": [
            {
                "id": str(first + n),
                "messagesAdded": [{"message": {"id": i, "labelIds": ["INBOX"]}}],
            }
            for n, i in enumerate(ids)
        ],
    }
    if next_page:
        page["nextPageToken"] = next_page
    return page


@pytest.fixture
def google() -> FakeGoogle:
    return FakeGoogle()


@pytest.fixture
async def connector(google) -> AsyncIterator[GmailConnector]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(google.handler)) as http:
        client = GmailClient(http, "cid", "secret", "https://api.example/cb")
        yield GmailConnector(
            client,
            client_id="cid",
            topic="projects/p/topics/t",
            push_audience=None,
            push_service_account=None,
        )


CREDS = {"refresh_token": "r1"}


def test_authorization_url_requests_offline_access(connector):
    url = connector.authorization_url("st4te")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    assert query["scope"] == f"{READ_SCOPE} {SEND_SCOPE}"
    assert query["access_type"] == "offline"
    assert query["prompt"] == "consent"
    assert query["state"] == "st4te"
    assert query["client_id"] == "cid"
    assert query["redirect_uri"] == "https://api.example/cb"
    assert query["response_type"] == "code"
    assert query["include_granted_scopes"] == "true"


def test_authorization_url_asks_to_read_and_send(connector):
    url = connector.authorization_url("st4te")
    query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    assert query["scope"] == (
        "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"
    )


@pytest.mark.parametrize(
    ("granted", "can_send"),
    [
        (f"{READ_SCOPE} {SEND_SCOPE}", True),
        # Google's granular consent lets the owner untick a scope.
        (READ_SCOPE, False),
        (None, False),
    ],
)
async def test_complete_authorization_reports_send_permission(connector, google, granted, can_send):
    google.granted_scope = granted
    account = await connector.complete_authorization("code")
    assert account.can_send is can_send


async def test_complete_authorization_without_refresh_token_raises(connector, google):
    google.refresh_token = None
    with pytest.raises(MissingRefreshToken):
        await connector.complete_authorization("code")


async def test_complete_authorization_returns_lowercase_address(connector, google):
    google.email = "Owner@Shop.IN"
    account = await connector.complete_authorization("code")
    assert account.email_address == "owner@shop.in"
    assert account.credentials == {"refresh_token": "r1"}


async def test_first_fetch_backfills_and_takes_cursor_from_profile(connector, google):
    google.listed_ids = ["m1", "m2"]
    google.add_message("m1", sender="Riya <Riya@Customer.in>", subject="Order", body="Where?")
    google.add_message("m2")

    result = await connector.fetch_changes(CREDS, None)

    assert result.cursor == "500"
    assert [m.provider_message_id for m in result.messages] == ["m1", "m2"]
    first = result.messages[0]
    assert (first.sender, first.subject, first.body) == ("riya@customer.in", "Order", "Where?")
    assert first.received_at.timestamp() == 1.0
    assert first.thread_id == "t-m1"
    assert google.calls.index("profile") < google.calls.index(f"list:{BACKFILL_QUERY}")
    assert first.in_spam is False


async def test_first_fetch_with_spam_backfills_inbox_and_spam(connector, google):
    google.listed_ids = ["m1", "s1"]
    google.add_message("m1")
    google.add_message("s1", labels=("SPAM",))

    result = await connector.fetch_changes(CREDS, None, include_spam=True)

    assert f"list:{BACKFILL_WITH_SPAM_QUERY}" in google.calls
    assert [(m.provider_message_id, m.in_spam) for m in result.messages] == [
        ("m1", False),
        ("s1", True),
    ]


async def test_spam_is_skipped_unless_asked(connector, google):
    google.listed_ids = ["m1", "s1"]
    google.add_message("m1")
    google.add_message("s1", labels=("SPAM",))

    result = await connector.fetch_changes(CREDS, None)

    assert [m.provider_message_id for m in result.messages] == ["m1"]


async def test_fetch_recent_spam_reads_spam_and_moves_no_cursor(connector, google):
    google.listed_ids = ["s1", "gone-to-trash"]
    google.add_message("s1", labels=("SPAM", "UNREAD"))
    google.add_message("gone-to-trash", labels=("TRASH",))

    messages = await connector.fetch_recent_spam(CREDS)

    assert [(m.provider_message_id, m.in_spam) for m in messages] == [("s1", True)]
    assert google.calls == ["token", f"list:{SPAM_BACKFILL_QUERY}", "get:s1", "get:gone-to-trash"]


async def test_subscribe_watches_spam_when_asked(connector, google):
    await connector.subscribe(CREDS, {}, include_spam=True)
    assert google.watch_labels == ["INBOX", "SPAM"]
    await connector.subscribe(CREDS, {})
    assert google.watch_labels == ["INBOX"]


async def test_fetch_follows_every_history_page(connector, google):
    google.history_pages = {
        None: _history_page("600", ["m1"], next_page="p2"),
        "p2": _history_page("700", ["m2"]),
    }
    google.add_message("m1")
    google.add_message("m2")

    result = await connector.fetch_changes(CREDS, "400")

    assert [m.provider_message_id for m in result.messages] == ["m1", "m2"]
    # Ruling R8: the first page's historyId, not the last page's.
    assert result.cursor == "600"
    assert google.calls.count("token") == 1


async def test_expired_cursor_falls_back_to_backfill(connector, google):
    google.expired_pages = {None}
    google.listed_ids = ["m1"]
    google.add_message("m1")

    result = await connector.fetch_changes(CREDS, "1")

    assert [m.provider_message_id for m in result.messages] == ["m1"]
    assert result.cursor == "500"
    assert google.calls.count("token") == 1


async def test_cursor_expiring_mid_pagination_falls_back_to_backfill(connector, google):
    google.history_pages = {None: _history_page("600", ["m1"], next_page="p2")}
    google.expired_pages = {"p2"}
    google.listed_ids = ["m2"]
    google.add_message("m1")
    google.add_message("m2")

    result = await connector.fetch_changes(CREDS, "400")

    # Ids from the pages before the 404 are dropped: the backfill replaces them.
    assert [m.provider_message_id for m in result.messages] == ["m2"]
    assert result.cursor == "500"


async def test_message_deleted_between_list_and_get_is_skipped(connector, google):
    google.history_pages = {None: _history_page("600", ["gone", "m1"])}
    google.add_message("m1")

    result = await connector.fetch_changes(CREDS, "400")

    assert "get:gone" in google.calls
    assert [m.provider_message_id for m in result.messages] == ["m1"]


def history_starts(google: FakeGoogle) -> list[str]:
    """The startHistoryId of each history request, in order."""
    return [c.split(":")[1] for c in google.calls if c.startswith("history:")]


async def test_history_gap_is_fetched_in_capped_batches(connector, google):
    # 250 new messages, two per record, records 1001..1125, served 40 records per page.
    assert MAX_MESSAGES_PER_FETCH == 100
    google.history_records = [(1000 + n, [f"m{2 * n - 1}", f"m{2 * n}"]) for n in range(1, 126)]
    for n in range(1, 251):
        google.add_message(f"m{n}")

    first = await connector.fetch_changes(CREDS, "1000")

    assert len(first.messages) == 100
    assert first.has_more is True
    # The last record fully taken: Gmail lists records after it on the next fetch.
    assert first.cursor == "1050"
    # The walk stopped inside the second page: no third page was requested.
    assert history_starts(google) == ["1000", "1000"]

    google.calls.clear()
    second = await connector.fetch_changes(CREDS, first.cursor)
    assert history_starts(google)[0] == "1050"
    assert (len(second.messages), second.has_more, second.cursor) == (100, True, "1100")

    third = await connector.fetch_changes(CREDS, second.cursor)
    # Every page read: the cursor is the first page's historyId again (ruling R8).
    assert (len(third.messages), third.has_more, third.cursor) == (50, False, "5000")

    fetched = [m.provider_message_id for r in (first, second, third) for m in r.messages]
    assert sorted(fetched) == sorted(f"m{n}" for n in range(1, 251))


async def test_single_record_larger_than_cap_is_taken_whole(connector, google):
    big = [f"b{n}" for n in range(150)]
    google.history_records = [(1001, big), (1002, ["m1"])]
    for message_id in [*big, "m1"]:
        google.add_message(message_id)

    first = await connector.fetch_changes(CREDS, "1000")

    # Stopping before the record would never move the cursor: take it whole instead.
    assert [m.provider_message_id for m in first.messages] == big
    assert (first.cursor, first.has_more) == ("1001", True)

    second = await connector.fetch_changes(CREDS, first.cursor)
    assert [m.provider_message_id for m in second.messages] == ["m1"]
    assert (second.cursor, second.has_more) == ("5000", False)


async def test_capped_history_always_advances_even_if_start_record_is_included(connector, google):
    google.history_start_inclusive = True
    big = [f"b{n}" for n in range(150)]
    google.history_records = [(1001, big), (1002, ["m1"]), (1003, ["m2"])]
    for message_id in [*big, "m1", "m2"]:
        google.add_message(message_id)

    cursor, fetched = "1000", []
    for _ in range(5):
        result = await connector.fetch_changes(CREDS, cursor)
        fetched += [m.provider_message_id for m in result.messages]
        # Never the same cursor back with more to read: that would sync the mailbox forever.
        assert int(result.cursor) > int(cursor)
        cursor = result.cursor
        if not result.has_more:
            break
    else:
        pytest.fail("the capped history never finished")

    assert cursor == "5000"
    # The start record is not read again: its mail came with the batch that ended on it.
    assert fetched == [*big, "m1", "m2"]


@pytest.mark.parametrize("status", [400, 410])
async def test_400_and_410_on_message_are_skipped(connector, google, caplog, status):
    google.history_pages = {None: _history_page("600", ["bad", "m1"])}
    google.message_errors["bad"] = status
    google.add_message("m1")

    with caplog.at_level(logging.WARNING, logger="herald_server.connectors.gmail.connector"):
        result = await connector.fetch_changes(CREDS, "400")

    assert [m.provider_message_id for m in result.messages] == ["m1"]
    assert result.cursor == "600"
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("bad" in w and "MessageUnavailable" in w for w in warnings)
    assert "leak-me-xyz" not in caplog.text


async def test_other_403_on_message_fails_the_fetch(connector, google):
    # insufficientPermissions, domainPolicy and the like refuse every message of the account,
    # not this one: skipping would move the cursor past mail that was never read.
    google.history_pages = {None: _history_page("600", ["m1", "m2"])}
    google.add_message("m1")
    google.message_errors["m2"] = 403

    with pytest.raises(httpx.HTTPStatusError):
        await connector.fetch_changes(CREDS, "400")


async def test_408_on_message_fails_the_fetch(connector, google):
    google.history_pages = {None: _history_page("600", ["slow", "m1"])}
    google.message_errors["slow"] = 408
    google.add_message("m1")

    with pytest.raises(httpx.HTTPStatusError):
        await connector.fetch_changes(CREDS, "400")


async def test_server_error_on_a_message_fails_the_fetch(connector, google):
    google.history_pages = {None: _history_page("600", ["flaky", "m1"])}
    google.message_errors["flaky"] = 503
    google.add_message("m1")

    # A 5xx may pass: fail the fetch so the cursor stays and the next sync reads it again.
    with pytest.raises(httpx.HTTPStatusError):
        await connector.fetch_changes(CREDS, "400")


async def test_message_without_inbox_label_is_skipped(connector, google):
    google.listed_ids = ["archived", "m1"]
    google.add_message("archived", labels=("CATEGORY_UPDATES",))
    google.add_message("m1")

    result = await connector.fetch_changes(CREDS, None)

    assert [m.provider_message_id for m in result.messages] == ["m1"]


async def test_backfill_skips_mail_the_owner_sent(connector, google):
    google.listed_ids = ["own", "m1"]
    google.add_message("own", labels=("INBOX", "SENT"))
    google.add_message("m1")

    result = await connector.fetch_changes(CREDS, None)

    assert [m.provider_message_id for m in result.messages] == ["m1"]


async def test_duplicate_ids_across_pages_fetched_once(connector, google):
    google.history_pages = {
        None: _history_page("600", ["m1", "m2"], next_page="p2"),
        "p2": _history_page("700", ["m2", "m1", "m3"]),
    }
    for message_id in ("m1", "m2", "m3"):
        google.add_message(message_id)

    result = await connector.fetch_changes(CREDS, "400")

    assert [m.provider_message_id for m in result.messages] == ["m1", "m2", "m3"]
    assert google.calls.count("get:m1") == 1
    assert google.calls.count("get:m2") == 1


async def test_unparseable_message_is_skipped(connector, google, caplog):
    google.listed_ids = ["bad", "good"]
    google.add_message("good")
    google.messages["bad"] = ("!!!not base64!!!", ["INBOX"])

    with caplog.at_level(logging.WARNING, logger="herald_server.connectors.gmail.connector"):
        result = await connector.fetch_changes(CREDS, None)

    assert [m.provider_message_id for m in result.messages] == ["good"]
    assert result.cursor == "500"
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("bad" in message for message in warnings)


async def test_subscribe_watches_topic_and_returns_expiry(connector, google):
    subscription = await connector.subscribe(CREDS, {})

    assert google.calls == ["token", "watch"]
    assert subscription.expires_at is not None
    assert subscription.expires_at.timestamp() == 2.0
    assert subscription.provider_state == {}


async def test_redirect_uri_has_no_double_slash_when_public_url_ends_in_slash():
    settings = Settings(
        token_key="k",
        google_client_id="cid",
        google_client_secret="secret",
        gmail_topic="projects/p/topics/t",
        public_api_url="https://api.example/",
    )
    async with httpx.AsyncClient() as http:
        connector = build_connectors(settings, http)["gmail"]
    query = parse_qs(urlsplit(connector.authorization_url("s")).query)
    # Google matches the redirect URI exactly: "//api" would fail the code exchange.
    assert query["redirect_uri"] == ["https://api.example/api/oauth/gmail/callback"]


async def test_build_connectors_includes_gmail_when_configured():
    settings = Settings(
        token_key="k",
        google_client_id="cid",
        google_client_secret="secret",
        gmail_topic="projects/p/topics/t",
    )
    async with httpx.AsyncClient() as http:
        connectors = build_connectors(settings, http)
    assert isinstance(connectors["gmail"], GmailConnector)
    assert connectors["gmail"].provider == "gmail"


async def test_send_reply_refreshes_and_sends_in_thread(connector, google):
    sent = []
    inner = google.handler

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == MESSAGES + "/send":
            google.calls.append("send")
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "m9"})
        return inner(request)

    connector._client._http._transport = httpx.MockTransport(handler)
    result = await connector.send_reply(
        CREDS,
        OutboundReply(
            from_address="owner@shop.in",
            to_address="cust@x.in",
            subject="Re: Hi",
            body="Hello back",
            in_reply_to="<a@x.in>",
            references="<a@x.in>",
            provider_thread_id="t1",
        ),
    )
    assert result.provider_message_id == "m9"
    assert google.calls == ["token", "send"]
    assert sent[0]["threadId"] == "t1"
    raw = sent[0]["raw"]
    msg = email.message_from_bytes(
        base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)), policy=email.policy.default
    )
    assert msg["In-Reply-To"] == "<a@x.in>"
    assert msg["Subject"] == "Re: Hi"
