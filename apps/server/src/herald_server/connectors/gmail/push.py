"""Verify Google Pub/Sub push requests and decode the Gmail notification inside them."""

import base64
import binascii
import json
from collections.abc import Callable
from functools import cache
from typing import Any

import jwt

from herald_server.connectors.base import PushIgnored, PushNotice, PushRejected

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"


@cache
def _jwk_client() -> jwt.PyJWKClient:
    # Created on first use so importing this module does no work; PyJWKClient caches the keys.
    return jwt.PyJWKClient(GOOGLE_CERTS_URL)


def google_signing_key(token: str) -> Any:
    """Look up Google's public key for this token. Blocking HTTP: call it off the event loop."""
    return _jwk_client().get_signing_key_from_jwt(token).key


def verify_push_token(
    token: str,
    *,
    audience: str,
    service_account: str,
    signing_key_for: Callable[[str], Any],
) -> None:
    """Raise PushRejected unless Google signed `token` for our audience and service account.

    Anyone can POST to the push URL, so this check is the only thing that proves the request
    came from our Pub/Sub subscription. Never log or echo the token.
    """
    try:
        key = signing_key_for(token)
        # Pinning RS256 stops algorithm-confusion tricks (alg=none, HS256 with a public key).
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=audience)
    except Exception as exc:
        raise PushRejected("push token failed verification") from exc
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise PushRejected("push token has an unexpected issuer")
    # The audience is not enough: any Google service account can mint a token for our URL.
    if claims.get("email") != service_account or claims.get("email_verified") is not True:
        raise PushRejected("push token is not from the expected service account")


def decode_envelope(body: bytes) -> PushNotice:
    """Read the Gmail address out of a Pub/Sub push body. Raises PushIgnored if unusable."""
    try:
        envelope = json.loads(body)
        data = base64.b64decode(envelope["message"]["data"], validate=True)
        address = json.loads(data)["emailAddress"]
        if not isinstance(address, str) or not address:
            raise ValueError("no address")
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise PushIgnored("push body is not a Gmail notification") from exc
    return PushNotice(email_address=address.lower())
