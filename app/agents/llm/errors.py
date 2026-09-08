"""Errors raised by the agent language-model client."""


class AgentLlmError(Exception):
    """Base error for the agent language-model client."""


class AgentLlmConfigError(AgentLlmError):
    """Raised when LLM settings are missing or unsafe."""


class AgentLlmRequestError(AgentLlmError):
    """Raised when the provider cannot be reached."""


class AgentLlmResponseError(AgentLlmError):
    """Raised when the provider response cannot be trusted or parsed."""
