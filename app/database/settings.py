from functools import lru_cache
from urllib.parse import quote

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """ PostgreSQL database settings """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    postgres_user: str = Field(min_length=1, max_length=63, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    postgres_password: SecretStr = Field(min_length=5)
    postgres_db: str = Field(min_length=1, max_length=63, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    postgres_host: str = Field(default="127.0.0.1", min_length=1)
    postgres_port: int = Field(default=5432, ge=1, le=65535)

    # SQLAlchemy connection pool size
    database_pool_size: int = Field(
        default=5,
        ge=1,
        le=50,
    )
    # Additional connections allowed under load
    database_max_overflow: int = Field(
        default=10,
        ge=0,
        le=100,
    )
    # Whether to log SQL statements
    database_echo: bool = False

    @property
    def async_database_url(self) -> str:
        """ generate database url for SQLAlchemy to consume """

        encoded_user= quote(self.postgres_user, safe="")
        encoded_password = quote(self.postgres_password.get_secret_value(), safe="")
        encoded_database = quote(self.postgres_db, safe="")

        return (
            f"postgresql+asyncpg://"
            f"{encoded_user}:{encoded_password}"
            f"@{self.postgres_host}:{self.postgres_port}"
            f"/{encoded_database}"
        )

@lru_cache
def get_database_settings() -> DatabaseSettings:
    """ get database settings from environment variables """

    return DatabaseSettings() # type: ignore[call-arg]