from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
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
    # Read here because .env values never reach os.environ, where the SDK would look.
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")

    ntfy_url: str = "https://ntfy.sh"
    ntfy_topic: str | None = None
    web_url: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
