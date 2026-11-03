"""Tests for Pub/Sub push verification and notification decoding."""

import base64
import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from herald_server.connectors.base import PushIgnored, PushRejected
from herald_server.connectors.gmail.client import GmailClient
from herald_server.connectors.gmail.connector import GmailConnector

AUDIENCE = "https://herald.example/webhooks/gmail"
SERVICE_ACCOUNT = "push@proj.iam.gserviceaccount.com"

# One key per module: RSA generation is the slow part of these tests.
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(key=KEY, drop: tuple[str, ...] = (), **overrides) -> str:
    claims = {
        "iss": "https://accounts.google.com",
        "aud": AUDIENCE,
        "email": SERVICE_ACCOUNT,
        "email_verified": True,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    claims.update(overrides)
    for name in drop:
        claims.pop(name)
    return jwt.encode(claims, key, algorithm="RS256")


def _body(address: str = "Owner@Shop.in", data: str | None = None) -> bytes:
    if data is None:
        payload = json.dumps({"emailAddress": address, "historyId": 7}).encode()
        data = base64.b64encode(payload).decode()
    return json.dumps({"message": {"data": data}}).encode()


def _headers(token: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token or _token()}"}


@pytest.fixture
async def make_connector():
    async with httpx.AsyncClient() as http:
        client = GmailClient(http, "cid", "secret", "https://api.example/cb")

        def make(audience: str | None = AUDIENCE, account: str | None = SERVICE_ACCOUNT):
            return GmailConnector(
                client,
                client_id="cid",
                topic="projects/p/topics/t",
                push_audience=audience,
                push_service_account=account,
                signing_key_for=lambda _: KEY.public_key(),
            )

        yield make


async def test_valid_push_returns_address(make_connector):
    notice = await make_connector().parse_push(_headers(), _body())
    assert notice.email_address == "owner@shop.in"


async def test_lowercase_authorization_header_is_accepted(make_connector):
    headers = {"authorization": f"Bearer {_token()}"}
    notice = await make_connector().parse_push(headers, _body())
    assert notice.email_address == "owner@shop.in"


async def test_wrong_audience_is_rejected(make_connector):
    with pytest.raises(PushRejected):
        await make_connector().parse_push(_headers(_token(aud="https://evil.example")), _body())


async def test_wrong_service_account_is_rejected(make_connector):
    with pytest.raises(PushRejected):
        await make_connector().parse_push(_headers(_token(email="x@y.com")), _body())


async def test_unverified_email_is_rejected(make_connector):
    with pytest.raises(PushRejected):
        await make_connector().parse_push(_headers(_token(email_verified=False)), _body())


async def test_wrong_issuer_is_rejected(make_connector):
    with pytest.raises(PushRejected):
        await make_connector().parse_push(_headers(_token(iss="https://evil.example")), _body())


async def test_token_signed_by_other_key_is_rejected(make_connector):
    with pytest.raises(PushRejected):
        await make_connector().parse_push(_headers(_token(key=OTHER_KEY)), _body())


async def test_expired_token_is_rejected(make_connector):
    with pytest.raises(PushRejected):
        await make_connector().parse_push(_headers(_token(exp=int(time.time()) - 60)), _body())


async def test_token_expired_within_clock_skew_is_accepted(make_connector):
    # Google's clock and ours may differ by a few seconds; 30 s of leeway absorbs that.
    token = _token(exp=int(time.time()) - 10)
    notice = await make_connector().parse_push(_headers(token), _body())
    assert notice.email_address == "owner@shop.in"


async def test_token_without_exp_is_rejected(make_connector):
    with pytest.raises(PushRejected):
        await make_connector().parse_push(_headers(_token(drop=("exp",))), _body())


async def test_missing_authorization_header_is_rejected(make_connector):
    with pytest.raises(PushRejected):
        await make_connector().parse_push({}, _body())


async def test_non_bearer_scheme_is_rejected(make_connector):
    with pytest.raises(PushRejected):
        await make_connector().parse_push({"Authorization": f"Basic {_token()}"}, _body())


async def test_push_rejected_when_audience_not_configured(make_connector):
    with pytest.raises(PushRejected):
        await make_connector(audience=None).parse_push(_headers(), _body())


async def test_push_rejected_when_service_account_not_configured(make_connector):
    with pytest.raises(PushRejected):
        await make_connector(account=None).parse_push(_headers(), _body())


async def test_malformed_data_is_ignored(make_connector):
    with pytest.raises(PushIgnored):
        await make_connector().parse_push(_headers(), _body(data="%%% not base64 %%%"))


async def test_malformed_body_is_ignored(make_connector):
    with pytest.raises(PushIgnored):
        await make_connector().parse_push(_headers(), b"not json")
