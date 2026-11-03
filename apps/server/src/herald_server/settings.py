from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from herald_core.model import DEFAULT_MODEL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HERALD_", env_file=(".env", "../../.env"), extra="ignore"
    )

    database_url: str = "postgresql+psycopg://herald:herald@localhost:5432/herald"
    redis_url: str = "redis://localhost:6379/0"

    # "memory" and "inline" run everything in one process with no Redis (tests, quick demos).
    bus: Literal["redis", "memory"] = "redis"
    queue: Literal["arq", "inline"] = "arq"

    model_provider: Literal["anthropic", "fake"] = "fake"
    model_name: str = DEFAULT_MODEL

    web_url: str = "http://localhost:5173"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
