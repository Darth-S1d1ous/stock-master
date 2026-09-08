"""OpenAI-compatible chat client for the condition-authoring agent.

LLM output is untrusted. This package only transports messages; it never
writes theses or conditions.
"""

from app.agents.llm.client import OpenAICompatibleLlmClient
from app.agents.llm.errors import (
    AgentLlmConfigError,
    AgentLlmError,
    AgentLlmRequestError,
    AgentLlmResponseError,
)
from app.agents.llm.providers import (
    LLM_PROVIDERS,
    AgentLlmProvider,
    LlmProviderSpec,
    get_provider_spec,
    register_llm_provider,
    registered_llm_providers,
)
from app.agents.llm.settings import AgentLlmSettings, get_agent_llm_settings
from app.agents.llm.types import (
    AgentLlmClient,
    LlmChatMessage,
    LlmCompletion,
    LlmToolCall,
)

__all__ = [
    "LLM_PROVIDERS",
    "AgentLlmClient",
    "AgentLlmConfigError",
    "AgentLlmError",
    "AgentLlmProvider",
    "AgentLlmRequestError",
    "AgentLlmResponseError",
    "AgentLlmSettings",
    "LlmChatMessage",
    "LlmCompletion",
    "LlmProviderSpec",
    "LlmToolCall",
    "OpenAICompatibleLlmClient",
    "get_agent_llm_settings",
    "get_provider_spec",
    "register_llm_provider",
    "registered_llm_providers",
]
