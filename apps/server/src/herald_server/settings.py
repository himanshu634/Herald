import os
from functools import lru_cache
from typing import Literal

from dotenv import dotenv_values
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HERALD_",
        env_file=(".env", "../../.env"),
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = "postgresql+psycopg://herald:herald@localhost:5432/herald"
    redis_url: str = "redis://localhost:6379/0"

    # "memory" and "inline" run everything in one process with no Redis (tests, quick demos).
    bus: Literal["redis", "memory"] = "redis"
    queue: Literal["arq", "inline"] = "arq"

    # A name from the herald.model_providers entry points. Not a Literal: plug-ins add names.
    model_provider: str = "openrouter"
    # Empty means the provider's default model.
    model_name: str | None = None

    # Send the traceback in 500 responses, so the web app shows it. Dev only: it leaks internals.
    debug: bool = False
    # Level for Herald's own loggers. INFO prints one line per email arrival and pipeline step.
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Dev-only tracing to a local Langfuse (see "Tracing (dev)" in docs/architecture.md).
    # Tracing is on only when both keys are set and not empty.
    # Production images have no Langfuse package, so it stays off there.
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str = "http://localhost:3000"

    web_url: str = "http://localhost:5173"

    # The worker's triage pipeline and its tools reach the database only through the API's
    # internal routes (/internal/v1). The worker calls this base URL and sends this token.
    # Required for the arq queue. The inline queue makes a random one per process.
    internal_api_url: str = "http://localhost:8000"
    internal_token: SecretStr | None = None

    # Fernet key that encrypts mailbox credentials and signs OAuth state.
    # Generate one with Fernet.generate_key() from the cryptography package.
    token_key: str | None = None
    # Public base URL of this API, used to build OAuth redirect and webhook URLs.
    public_api_url: str = "http://localhost:8000"

    # Google OAuth client for the Gmail connector.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    # Pub/Sub topic Gmail publishes to, like projects/<project>/topics/herald-gmail.
    gmail_topic: str | None = None
    # Audience and service account email expected in the Pub/Sub push JWT.
    gmail_push_audience: str | None = None
    gmail_push_service_account: str | None = None

    def secret(self, name: str) -> str | None:
        """An API key by its own variable name, from the environment, then the .env files.

        pydantic-settings reads .env into fields only and never exports it to os.environ, so a
        key kept in .env would never reach a provider that reads a bare variable. The key has
        no HERALD_ prefix, so it is not a field. Empty counts as unset.
        """
        if value := os.environ.get(name):
            return value
        files = self.model_config.get("env_file") or ()
        if isinstance(files, str | os.PathLike):
            files = (files,)
        found = None
        # Later files win, as in pydantic-settings.
        for file in files:
            found = dotenv_values(file).get(name) or found
        return found


@lru_cache
def get_settings() -> Settings:
    return Settings()
