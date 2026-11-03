"""The shared secret the worker sends on every internal call."""

import secrets

from herald_server.settings import Settings

TOKEN_HEADER = "X-Herald-Internal-Token"
MIN_TOKEN_CHARS = 24


def internal_token(settings: Settings, *, allow_random: bool) -> str:
    value = settings.internal_token.get_secret_value() if settings.internal_token else ""
    if value:
        if len(value) < MIN_TOKEN_CHARS:
            raise RuntimeError(f"HERALD_INTERNAL_TOKEN must be at least {MIN_TOKEN_CHARS} chars")
        return value
    if allow_random:
        # Inline queue: the only caller is this process's own in-memory client, so a fresh
        # random token is enough and nothing needs setting up.
        return secrets.token_urlsafe(32)
    # Fail closed: a worker and an API that disagree on the token would leave every email
    # untriaged, and an API with no token must never mean open internal routes.
    raise RuntimeError("HERALD_INTERNAL_TOKEN is not set (needed by the API and the arq worker)")
