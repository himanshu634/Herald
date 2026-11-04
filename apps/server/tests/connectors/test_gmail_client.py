import json
from datetime import UTC, datetime

import httpx
import pytest

from herald_server.connectors.base import AuthRevoked, RateLimited, SendNotAllowed, SendRejected
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
    assert httpx.URL(seen["url"]).params.get_list("historyTypes") == [
        "messageAdded",
        "labelAdded",
    ]
    # Herald may read two labels and Gmail filters on one, so labels are checked per message.
    assert "labelId" not in seen["params"]
    assert seen["auth"] == "Bearer tok"


SPAM_HISTORY = {
    "historyId": "300",
    "history": [
        {"id": "201", "messagesAdded": [{"message": {"id": "s1", "labelIds": ["SPAM"]}}]},
        # Marked "not spam": the message gains INBOX.
        {
            "id": "202",
            "labelsAdded": [
                {"message": {"id": "s2", "labelIds": ["INBOX"]}, "labelIds": ["INBOX"]}
            ],
        },
        # A star is a new label too, but not one Herald reads.
        {
            "id": "203",
            "labelsAdded": [
                {"message": {"id": "m4", "labelIds": ["INBOX", "STARRED"]}, "labelIds": ["STARRED"]}
            ],
        },
        # Moved to the inbox and archived again before the sync ran.
        {
            "id": "204",
            "labelsAdded": [{"message": {"id": "m5", "labelIds": []}, "labelIds": ["INBOX"]}],
        },
    ],
}


async def test_list_history_reads_mail_moved_into_the_inbox_but_not_spam():
    def handler(request):
        return httpx.Response(200, json=SPAM_HISTORY)

    page = await make_client(handler).list_history("tok", "100")
    assert page.records == [
        HistoryRecord("201", []),
        HistoryRecord("202", ["s2"]),
        HistoryRecord("203", []),
        HistoryRecord("204", []),
    ]


async def test_list_history_reads_spam_when_asked():
    def handler(request):
        return httpx.Response(200, json=SPAM_HISTORY)

    page = await make_client(handler).list_history("tok", "100", include_spam=True)
    assert [r.message_ids for r in page.records] == [["s1"], ["s2"], [], []]


async def test_watch_includes_spam_when_asked():
    seen = {}

    def handler(request):
        seen["json"] = json.loads(request.read())
        return httpx.Response(200, json={"historyId": "5", "expiration": "1762790400000"})

    await make_client(handler).watch("tok", "projects/p/topics/t", include_spam=True)
    assert seen["json"]["labelIds"] == ["INBOX", "SPAM"]


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


@pytest.mark.parametrize("reason", ["dailyLimitExceeded", "quotaExceeded"])
async def test_daily_limit_403_raises_rate_limited(reason):
    def handler(request):
        return httpx.Response(403, json={"error": {"errors": [{"reason": reason}]}})

    with pytest.raises(RateLimited):
        await make_client(handler).get_raw_message("tok", "m1")


@pytest.mark.parametrize("status", [400, 410])
async def test_get_raw_message_400_and_410_raise_message_unavailable(status):
    def handler(request):
        return httpx.Response(status, json={"error": {"message": "leak-me-xyz"}})

    with pytest.raises(MessageUnavailable) as exc:
        await make_client(handler).get_raw_message("tok", "m1")
    assert "leak-me-xyz" not in str(exc.value)


@pytest.mark.parametrize("status", [403, 408])
async def test_get_raw_message_other_4xx_raises_http_error(status):
    def handler(request):
        return httpx.Response(
            status, json={"error": {"errors": [{"reason": "insufficientPermissions"}]}}
        )

    with pytest.raises(httpx.HTTPStatusError):
        await make_client(handler).get_raw_message("tok", "m1")


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


async def test_send_posts_raw_and_thread():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"id": "m9"})

    client = make_client(handler)
    assert await client.send_message("acc", "RAW", "t1") == "m9"
    assert await client.send_message("acc", "RAW", None) == "m9"
    assert seen[0].method == "POST"
    assert seen[0].url.path.endswith("/messages/send")
    assert seen[0].headers["Authorization"] == "Bearer acc"
    assert json.loads(seen[0].content) == {"raw": "RAW", "threadId": "t1"}
    assert json.loads(seen[1].content) == {"raw": "RAW"}


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"errors": [{"reason": "insufficientPermissions"}], "message": "x"}},
        {"error": {"message": "Request had insufficient authentication scopes."}},
    ],
)
async def test_send_403_insufficient_scope_is_send_not_allowed(body):
    def handler(request):
        return httpx.Response(403, json=body)

    with pytest.raises(SendNotAllowed):
        await make_client(handler).send_message("acc", "RAW", None)


@pytest.mark.parametrize("status", [400, 404])
async def test_send_4xx_is_rejected(status):
    def handler(request):
        return httpx.Response(status, json={"error": {"message": "leak-me-xyz"}})

    with pytest.raises(SendRejected) as info:
        await make_client(handler).send_message("acc", "RAW", None)
    assert str(status) in str(info.value)
    assert "leak-me-xyz" not in str(info.value)


async def test_send_other_403_is_rejected():
    def handler(request):
        return httpx.Response(403, json={"error": {"message": "domain policy"}})

    with pytest.raises(SendRejected):
        await make_client(handler).send_message("acc", "RAW", None)


async def test_send_5xx_is_unknown():
    def handler(request):
        return httpx.Response(500, json={})

    with pytest.raises(httpx.HTTPStatusError):
        await make_client(handler).send_message("acc", "RAW", None)


async def test_send_transport_error_is_unknown():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(httpx.ReadTimeout):
        await make_client(handler).send_message("acc", "RAW", None)


async def test_send_429_is_rate_limited():
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "7"})

    with pytest.raises(RateLimited):
        await make_client(handler).send_message("acc", "RAW", None)


async def test_send_401_is_auth_revoked():
    def handler(request):
        return httpx.Response(401, json={})

    with pytest.raises(AuthRevoked):
        await make_client(handler).send_message("acc", "RAW", None)
