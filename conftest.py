import pytest

from herald_server.settings import get_settings


@pytest.fixture(autouse=True)
def _no_langfuse_keys(monkeypatch):
    # A developer's .env may hold Langfuse keys. Test runs must never send traces, and
    # cli.main in the eval tests reads get_settings(), so clear the keys and the settings cache.
    monkeypatch.setenv("HERALD_LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("HERALD_LANGFUSE_SECRET_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
