from datetime import UTC, datetime

import httpx
import pytest

from herald_server.connectors.base import AuthRevoked, RateLimited
from herald_server.connectors.gmail.client import (
    API,
    GmailClient,
    HistoryExpired,
    HistoryRecord,
    MessageGone,
    MessageUnavailable,
)


def make_client(handler) -> GmailClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GmailClient(http, "cid", "secret", "https://app/cb")


async def test_refresh_invalid_grant_raises_auth_revoked():
    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant"})

    with pytest.raises(AuthRevoked):
        await make_client(handler).refresh("r1")


async def test_list_history_404_raises_history_expired():
    def handler(request):
        return httpx.Response(404, json={"error": {"code": 404}})

    with pytest.raises(HistoryExpired):
        await make_client(handler).list_history("tok", "100")


async def test_list_history_keeps_inbox_and_drops_sent_and_drafts():
    body = {
        "historyId": "200",
        "history": [
            {"id": "101", "messagesAdded": [{"message": {"id": "m1", "labelIds": ["INBOX"]}}]},
            {"id": "102", "messagesAdded": [{"message": {"id": "m2", "labelIds": ["SENT"]}}]},
            {
                "id": "103",
                "messagesAdded": [{"message": {"id": "m3", "labelIds": ["DRAFT", "INBOX"]}}],
            },
        ],
    }

    def handler(request):
        return httpx.Response(200, json=body)

    page = await make_client(handler).list_history("tok", "100")
    # Records left with no inbox mail are kept, so the cursor can move past them.
    assert page.records == [
        HistoryRecord("101", ["m1"]),
        HistoryRecord("102", []),
        HistoryRecord("103", []),
    ]
    assert page.history_id == "200"
    assert page.next_page_token is None


async def test_list_history_sends_cursor_and_filters():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["params"] = dict(request.url.params)
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json={"historyId": "1"})

    await make_client(handler).list_history("tok", "100")
    assert seen["url"].startswith(f"{API}/history")
    assert seen["params"]["startHistoryId"] == "100"
    assert seen["params"]["historyTypes"] == "messageAdded"
    assert seen["params"]["labelId"] == "INBOX"
    assert seen["auth"] == "Bearer tok"


async def test_watch_sends_topic_and_inbox_filter():
    seen = {}

    def handler(request):
        seen["json"] = request.read()
        return httpx.Response(200, json={"historyId": "5", "expiration": "1762790400000"})

    result = await make_client(handler).watch("tok", "projects/p/topics/t")
    import json

    assert json.loads(seen["json"]) == {
        "topicName": "projects/p/topics/t",
        "labelIds": ["INBOX"],
        "labelFilterBehavior": "include",
    }
    assert result.history_id == "5"
    assert result.expiration == datetime(2025, 11, 10, 16, 0, tzinfo=UTC)


async def test_429_raises_rate_limited_with_retry_after():
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "12"})

    with pytest.raises(RateLimited) as exc:
        await make_client(handler).get_profile("tok")
    assert exc.value.retry_after == 12


async def test_403_user_rate_limit_raises_rate_limited():
    def handler(request):
        return httpx.Response(
            403, json={"error": {"errors": [{"reason": "userRateLimitExceeded"}]}}
        )

    with pytest.raises(RateLimited) as exc:
        await make_client(handler).get_profile("tok")
    assert exc.value.retry_after == 30


async def test_get_raw_message_404_raises_message_gone():
    def handler(request):
        return httpx.Response(404, json={})

    with pytest.raises(MessageGone):
        await make_client(handler).get_raw_message("tok", "m1")


@pytest.mark.parametrize("status", [400, 403, 410])
async def test_get_raw_message_other_4xx_raises_message_unavailable(status):
    def handler(request):
        return httpx.Response(status, json={"error": {"message": "leak-me-xyz"}})

    with pytest.raises(MessageUnavailable) as exc:
        await make_client(handler).get_raw_message("tok", "m1")
    assert "leak-me-xyz" not in str(exc.value)


async def test_get_raw_message_5xx_still_raises():
    def handler(request):
        return httpx.Response(503, json={})

    with pytest.raises(httpx.HTTPStatusError):
        await make_client(handler).get_raw_message("tok", "m1")


async def test_api_401_raises_auth_revoked():
    def handler(request):
        return httpx.Response(401, json={})

    with pytest.raises(AuthRevoked):
        await make_client(handler).get_profile("tok")


async def test_revoke_swallows_400():
    def handler(request):
        return httpx.Response(400, json={"error": "invalid_token"})

    await make_client(handler).revoke("tok")
