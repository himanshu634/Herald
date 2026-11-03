from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from herald_core.model import DEFAULT_MODEL


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

    model_provider: Literal["anthropic", "fake"] = "fake"
    model_name: str = DEFAULT_MODEL
    # Read here, not by the SDK: values in .env never reach os.environ, so a bare
    # AsyncAnthropic() would start without a key and fail on every email.
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")

    # Send the traceback in 500 responses, so the web app shows it. Dev only: it leaks internals.
    debug: bool = False
    # Level for Herald's own loggers. INFO prints one line per email arrival and pipeline step.
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Dev-only tracing to a local Langfuse (see docs). Tracing is on only when both keys are
    # set and not empty. Production images have no Langfuse package, so it stays off there.
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
