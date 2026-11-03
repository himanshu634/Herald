"""Thin REST client for Google OAuth and the Gmail API.

The only code that talks HTTP to Google. It maps Google's failures onto the connector errors
and never logs or embeds tokens in exception messages.
"""

from datetime import UTC, datetime
from typing import Any, NamedTuple

import httpx

from herald_server.connectors.base import AuthRevoked, RateLimited

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://gmail.googleapis.com/gmail/v1/users/me"

DEFAULT_RETRY_AFTER = 30.0
# 403 reasons that pass with time. The daily and project quotas reset on Google's side, so they
# are rate limits too: the job retries later and the cursor stays where it is.
_RATE_LIMIT_REASONS = {
    "rateLimitExceeded",
    "userRateLimitExceeded",
    "dailyLimitExceeded",
    "quotaExceeded",
}


class HistoryExpired(Exception):
    """Gmail no longer holds history from the cursor; a full resync is needed."""


class MessageGone(Exception):
    """The message was deleted before we fetched it."""


class MessageUnavailable(Exception):
    """Gmail refuses this one message for good (400 or 410 on the message get)."""


class TokenSet(NamedTuple):
    access_token: str
    refresh_token: str | None


class Profile(NamedTuple):
    email_address: str
    history_id: str


class WatchResult(NamedTuple):
    history_id: str
    expiration: datetime


class HistoryRecord(NamedTuple):
    id: str
    message_ids: list[str]  # inbox mail only; may be empty


class HistoryPage(NamedTuple):
    records: list[HistoryRecord]
    history_id: str
    next_page_token: str | None


class MessagePage(NamedTuple):
    message_ids: list[str]
    next_page_token: str | None


class RawMessage(NamedTuple):
    id: str
    raw: str
    label_ids: list[str]
    internal_date: datetime


def is_inbox_mail(label_ids: list[str]) -> bool:
    # Herald triages mail the owner received, not the owner's own sent mail or drafts
    # (mail sent to yourself carries both INBOX and SENT).
    return "INBOX" in label_ids and "SENT" not in label_ids and "DRAFT" not in label_ids


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _retry_after(response: httpx.Response) -> float:
    try:
        return float(response.headers["Retry-After"])
    except (KeyError, ValueError):
        # Missing, or an HTTP-date we do not parse: use the default.
        return DEFAULT_RETRY_AFTER


def _is_rate_limited(response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    error = _json(response).get("error")
    if not isinstance(error, dict):
        return False
    return any(e.get("reason") in _RATE_LIMIT_REASONS for e in error.get("errors", []))


def _ms_to_datetime(ms: str | int) -> datetime:
    return datetime.fromtimestamp(int(ms) / 1000, tz=UTC)


class GmailClient:
    def __init__(
        self, http: httpx.AsyncClient, client_id: str, client_secret: str, redirect_uri: str
    ) -> None:
        self._http = http
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    @property
    def redirect_uri(self) -> str:
        """The OAuth callback; the consent URL must name the same one the code exchange sends."""
        return self._redirect_uri

    async def _request(
        self, method: str, url: str, access: str | None, **kw: Any
    ) -> httpx.Response:
        """Send one request and map Google's auth and rate-limit failures onto our errors.

        Other statuses come back as is: 404 means different things for history and messages.
        """
        if access is not None:
            kw["headers"] = {**kw.get("headers", {}), "Authorization": f"Bearer {access}"}
        response = await self._http.request(method, url, **kw)
        if _is_rate_limited(response):
            raise RateLimited(_retry_after(response))
        if url == TOKEN_URL and response.status_code == 400:
            if _json(response).get("error") == "invalid_grant":
                raise AuthRevoked("Google rejected the grant")
        if url.startswith(API) and response.status_code == 401:
            raise AuthRevoked("Google rejected the access token")
        return response

    async def _api(self, method: str, path: str, access: str, **kw: Any) -> dict[str, Any]:
        response = await self._request(method, f"{API}{path}", access, **kw)
        response.raise_for_status()
        return _json(response)

    async def _token(self, data: dict[str, str]) -> dict[str, Any]:
        response = await self._request("POST", TOKEN_URL, None, data=data)
        response.raise_for_status()
        return _json(response)

    async def exchange_code(self, code: str) -> TokenSet:
        data = await self._token(
            {
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
                "grant_type": "authorization_code",
            }
        )
        return TokenSet(data["access_token"], data.get("refresh_token"))

    async def refresh(self, refresh_token: str) -> str:
        data = await self._token(
            {
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
            }
        )
        return data["access_token"]

    async def revoke(self, token: str) -> None:
        response = await self._request("POST", REVOKE_URL, None, data={"token": token})
        # 400 means the token is already revoked or expired: the goal is met.
        if response.status_code != 400:
            response.raise_for_status()

    async def get_profile(self, access: str) -> Profile:
        data = await self._api("GET", "/profile", access)
        return Profile(data["emailAddress"], str(data["historyId"]))

    async def watch(self, access: str, topic: str) -> WatchResult:
        data = await self._api(
            "POST",
            "/watch",
            access,
            json={"topicName": topic, "labelIds": ["INBOX"], "labelFilterBehavior": "include"},
        )
        return WatchResult(str(data["historyId"]), _ms_to_datetime(data["expiration"]))

    async def stop(self, access: str) -> None:
        await self._api("POST", "/stop", access)

    async def list_history(
        self, access: str, start_history_id: str, page_token: str | None = None
    ) -> HistoryPage:
        params = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
            "labelId": "INBOX",
            "maxResults": "500",
        }
        if page_token:
            params["pageToken"] = page_token
        response = await self._request("GET", f"{API}/history", access, params=params)
        if response.status_code == 404:
            raise HistoryExpired("start history id is too old")
        response.raise_for_status()
        data = _json(response)
        records: list[HistoryRecord] = []
        for record in data.get("history", []):
            ids = [
                added["message"]["id"]
                for added in record.get("messagesAdded", [])
                if is_inbox_mail(added["message"].get("labelIds", []))
            ]
            # A record left with no inbox mail is kept: the cursor may still move past it.
            records.append(HistoryRecord(str(record["id"]), ids))
        return HistoryPage(records, str(data["historyId"]), data.get("nextPageToken"))

    async def list_messages(
        self, access: str, q: str, max_results: int, page_token: str | None = None
    ) -> MessagePage:
        params = {"q": q, "maxResults": str(max_results)}
        if page_token:
            params["pageToken"] = page_token
        data = await self._api("GET", "/messages", access, params=params)
        return MessagePage([m["id"] for m in data.get("messages", [])], data.get("nextPageToken"))

    async def get_raw_message(self, access: str, message_id: str) -> RawMessage:
        response = await self._request(
            "GET", f"{API}/messages/{message_id}", access, params={"format": "raw"}
        )
        if response.status_code == 404:
            raise MessageGone(message_id)
        # 401 and rate limits were raised by _request already. 400 and 410 are about this one
        # message and will answer the same next time, so the connector skips it instead of
        # failing every sync at it. The message names the id only, never the response body.
        if response.status_code in (400, 410):
            raise MessageUnavailable(f"{message_id} answered {response.status_code}")
        # Every other status raises and fails the fetch, so the cursor does not move. A 403
        # (insufficientPermissions, domainPolicy, ...) refuses the whole account, not this
        # message, and a 408 or 5xx may pass: skipping them would lose mail for good.
        response.raise_for_status()
        data = _json(response)
        return RawMessage(
            data["id"],
            data["raw"],
            data.get("labelIds", []),
            _ms_to_datetime(data["internalDate"]),
        )
