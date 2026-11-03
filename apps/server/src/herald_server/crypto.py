"""Encrypt and sign small JSON secrets (mailbox credentials, OAuth state) with one Fernet key."""

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class BadSecret(Exception):
    """The token is tampered, expired, sealed with another key, or not valid JSON."""


class SecretBox:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key)

    def seal(self, data: dict[str, Any]) -> str:
        return self._fernet.encrypt(json.dumps(data).encode()).decode()

    def open(
        self, token: str, *, max_age: int | None = None, now: int | None = None
    ) -> dict[str, Any]:
        try:
            # `now` lets tests check expiry without sleeping.
            if now is not None:
                ttl = max_age if max_age is not None else 2**62
                raw = self._fernet.decrypt_at_time(token.encode(), ttl, now)
            else:
                raw = self._fernet.decrypt(token.encode(), ttl=max_age)
            return json.loads(raw)
        except (InvalidToken, ValueError) as exc:
            raise BadSecret("cannot open token") from exc
