from functools import lru_cache
from typing import Self
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.agents.llm.errors import AgentLlmConfigError
from app.agents.llm.providers import (
    AgentLlmProvider,
    LlmProviderSpec,
    get_provider_spec,
)

_PROMPT_VERSION_DEFAULT = "condition-author-v1"


class AgentLlmSettings(BaseSettings):
    """Environment-backed settings for an allowlisted OpenAI-compatible host."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    agent_llm_provider: AgentLlmProvider
    agent_llm_api_key: SecretStr | None = None
    agent_llm_openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("AGENT_LLM_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    agent_llm_nvidia_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("AGENT_LLM_NVIDIA_API_KEY", "NVIDIA_API_KEY"),
    )
    agent_llm_base_url: str | None = None
    agent_llm_model: str | None = Field(default=None, min_length=1, max_length=100)
    agent_llm_timeout_seconds: float = Field(default=30.0, gt=0)
    agent_llm_max_tokens: int = Field(default=4096, ge=1, le=128000)
    agent_llm_prompt_version: str = Field(
        default=_PROMPT_VERSION_DEFAULT,
        min_length=1,
        max_length=255,
    )

    @model_validator(mode="after")
    def bind_allowlisted_provider(self) -> Self:
        spec = self.provider_spec()
        self.agent_llm_base_url = _require_https_v1_host(
            self.agent_llm_base_url or spec.base_url,
            allowed_host=spec.host,
        )
        model = (self.agent_llm_model or spec.default_model).strip()
        if not model:
            raise ValueError("LLM model is required")
        self.agent_llm_model = model[:100]
        if not self.resolved_api_key():
            raise ValueError("An API key is required for the selected LLM provider")
        return self

    def provider_spec(self) -> LlmProviderSpec:
        return get_provider_spec(self.agent_llm_provider)

    def resolved_api_key(self) -> str:
        return self.provider_spec().api_key_from(self)

    @property
    def base_url(self) -> str:
        if self.agent_llm_base_url is None:
            raise AgentLlmConfigError("LLM base URL is not configured")
        return self.agent_llm_base_url

    @property
    def model(self) -> str:
        if self.agent_llm_model is None:
            raise AgentLlmConfigError("LLM model is not configured")
        return self.agent_llm_model


def _require_https_v1_host(value: str, *, allowed_host: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme != "https"
        or parsed.hostname != allowed_host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/v1"
    ):
        raise ValueError("Invalid LLM base URL")
    return normalized


@lru_cache
def get_agent_llm_settings() -> AgentLlmSettings:
    return AgentLlmSettings.model_validate({})
