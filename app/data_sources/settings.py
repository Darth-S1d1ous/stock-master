from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class DataSourceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    alpha_vantage_api_key: str = Field(default="", min_length=0)
    alpha_vantage_base_url: str = Field(
        default="https://www.alphavantage.co/query"
    )
    alpha_vantage_timeout_seconds: float = Field(default=10.0, gt=0)
    alpha_vantage_max_retries: int = Field(default=3, ge=0)
    alpha_vantage_rate_limit_per_minute: int = Field(default=25, ge=1)

    finnhub_api_key: str = Field(default="", min_length=0)
    finnhub_base_url: str = Field(default="https://finnhub.io")
    finnhub_timeout_seconds: float = Field(default=10.0, gt=0)
    finnhub_max_retries: int = Field(default=3, ge=0)

@lru_cache
def get_settings() -> DataSourceSettings:
    return DataSourceSettings()