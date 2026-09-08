from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from pydantic import SecretStr


class AgentLlmProvider(StrEnum):
    """Named OpenAI-compatible hosts the agent is allowed to call."""

    OPENAI = "openai"
    NVIDIA = "nvidia"


@dataclass(frozen=True, slots=True)
class LlmProviderSpec:
    """Fixed HTTPS endpoint, default model, and API-key field for one provider."""

    host: str
    base_url: str
    default_model: str
    api_key_attr: str

    def api_key_from(self, settings: object) -> str:
        """Read this provider's key, then the shared fallback key."""

        extra = getattr(settings, "model_extra", None) or {}
        provider_key = getattr(settings, self.api_key_attr, None)
        if provider_key is None:
            provider_key = extra.get(self.api_key_attr)
        shared_key = getattr(settings, "agent_llm_api_key", None)
        return _secret_value(provider_key) or _secret_value(shared_key)


_PROVIDERS: dict[AgentLlmProvider, LlmProviderSpec] = {}


def register_llm_provider(provider: AgentLlmProvider, spec: LlmProviderSpec) -> None:
    """Register an allowlisted OpenAI-compatible host.

    New providers extend this registry; key resolution does not change.
    """

    if not spec.api_key_attr.strip():
        raise ValueError("LLM provider api_key_attr is required")
    _PROVIDERS[provider] = spec


def get_provider_spec(provider: AgentLlmProvider) -> LlmProviderSpec:
    spec = _PROVIDERS.get(provider)
    if spec is None:
        raise ValueError("Unknown LLM provider")
    return spec


def registered_llm_providers() -> tuple[AgentLlmProvider, ...]:
    return tuple(_PROVIDERS)


def _secret_value(value: SecretStr | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, SecretStr):
        return value.get_secret_value().strip()
    return str(value).strip()


register_llm_provider(
    AgentLlmProvider.OPENAI,
    LlmProviderSpec(
        host="api.openai.com",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4.1-mini",
        api_key_attr="agent_llm_openai_api_key",
    ),
)
register_llm_provider(
    AgentLlmProvider.NVIDIA,
    LlmProviderSpec(
        host="integrate.api.nvidia.com",
        base_url="https://integrate.api.nvidia.com/v1",
        default_model="nvidia/nemotron-3.5-lightning-30b-a3b",
        api_key_attr="agent_llm_nvidia_api_key",
    ),
)

LLM_PROVIDERS: Mapping[AgentLlmProvider, LlmProviderSpec] = MappingProxyType(_PROVIDERS)
