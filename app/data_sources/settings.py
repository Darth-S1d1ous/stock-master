from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class DataSourceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    alpha_vantage_api_key: SecretStr = Field(default=SecretStr(""))
    alpha_vantage_base_url: str = Field(
        default="https://www.alphavantage.co/query"
    )
    alpha_vantage_timeout_seconds: float = Field(default=10.0, gt=0)
    alpha_vantage_max_retries: int = Field(default=3, ge=0)
    alpha_vantage_rate_limit_per_minute: int = Field(default=25, ge=1)

    finnhub_api_key: SecretStr = Field(default=SecretStr(""))
    finnhub_base_url: str = Field(default="https://finnhub.io")
    finnhub_timeout_seconds: float = Field(default=10.0, gt=0)
    finnhub_max_retries: int = Field(default=3, ge=0)

    @field_validator("alpha_vantage_base_url")
    @classmethod
    def validate_alpha_vantage_url(cls, value: str) -> str:
        return cls._validate_provider_url(
            value,
            allowed_host="www.alphavantage.co",
            required_path="/query",
        )

    @field_validator("finnhub_base_url")
    @classmethod
    def validate_finnhub_url(cls, value: str) -> str:
        return cls._validate_provider_url(
            value,
            allowed_host="finnhub.io",
            required_path="",
        )

    @staticmethod
    def _validate_provider_url(
        value: str,
        *,
        allowed_host: str,
        required_path: str,
    ) -> str:
        normalized = value.strip()
        parsed = urlsplit(normalized)
        if (
            parsed.scheme != "https"
            or parsed.hostname != allowed_host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != required_path.rstrip("/")
        ):
            raise ValueError(
                f"Provider URL must use the approved HTTPS endpoint for {allowed_host}"
            )
        return normalized.rstrip("/")

@lru_cache
def get_settings() -> DataSourceSettings:
    return DataSourceSettings()