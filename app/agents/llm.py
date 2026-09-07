"""OpenAI-compatible chat client for the condition-authoring agent.

LLM output is untrusted. This module only transports messages; it never
writes theses or conditions.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import lru_cache, partial
from typing import Any, Protocol, Self
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ALLOWED_LLM_HOSTS = frozenset({"api.openai.com"})
_PROMPT_VERSION_DEFAULT = "condition-author-v1"

class AgentLlmError(Exception):
    """Base error for the agent language-model client."""
class AgentLlmConfigError(AgentLlmError):
    """Raised when LLM settings are missing or unsafe."""
class AgentLlmRequestError(AgentLlmError):
    """Raised when the provider cannot be reached."""
class AgentLlmResponseError(AgentLlmError):
    """Raised when the provider response cannot be trusted or parsed."""

class AgentLlmSettings(BaseSettings):
    """Environment-backed settings for the OpenAI-compatible client."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    agent_llm_api_key: SecretStr
    agent_llm_base_url: str
    agent_llm_model: str
    agent_llm_timeout_seconds: float
    agent_llm_prompt_version: str = Field(
        default=_PROMPT_VERSION_DEFAULT,
        min_length=1,
        max_length=255,
    )

    @field_validator("agent_llm_base_url")
    @classmethod
    def require_approved_https_endpoint(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in _ALLOWED_LLM_HOSTS
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
    return AgentLlmSetting.model_validate({})


class LlmToolCall(BaseModel):
    """One function invocation requested by the model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any]

class LlmChatMessage(BaseModel):
    """One message in a chat session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(pattern=r"^(system|user|assistant|tool)$")
    content: str = Field(min_length=1, max_length=20000)
    tool_call_id: str | None = Field(default=None, min_length=1, max_length=100)
    tool_calls: tuple[LlmToolCall, ...] = ()

    @field_validator("tool_calls")
    @classmethod
    def tool_calls_only_on_assistant(
        cls,
        value: tuple[LlmToolCall, ...],
        info: Any,
    ) -> tuple[LlmToolCall, ...]:
        del info
        return value

class LlmCompletion(BaseModel):
    """Provider result after one non-streaming chat round."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str | None = Field(default=None, max_length=20000)
    tool_calls: tuple[LlmToolCall, ...] = ()
    model: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=50)
    finish_reason: str = Field(min_length=1, max_length=50)

class AgentLlmClient(Protocol):
    """Transport used by the orchestrator. Tests can stub this."""
    async def complete(
        self,
        *,
        messages: Sequence[LlmChatMessage],
        tools: Sequence[Mapping[str, Any]],
        prompt_version: str | None = None,
    ) -> LlmCompletion:
        """Return one assistant turn, which may include tool calls."""

class OpenAICompatibleLlmClient:
    """POST /chat/completions against an allowlisted OpenAI-compatible host."""
    def __init__(
        self,
        settings: AgentLlmSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:

        self._settings = settings or get_agent_llm_settings()
        if not self._settings.agent_llm_api_key.get_secret_value():
            raise AgentLlmConfigError("AGENT_LLM_API_KEY is required")
        self._provided_http_client = http_client
        self._owned_http_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        if self._provided_http_client is None:
            self._owned_http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.agent_llm_timeout_seconds),
                follow_redirects=False,
            )
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:

        del exc_type, exc_value, traceback
        if self._owned_http_client is not None:
            await self._owned_http_client.aclose()
            self._owned_http_client = None

    def _http_client(self) -> httpx.AsyncClient:
        if self._provided_http_client is not None:
            return self._provided_http_client
        if self._owned_http_client is None:
            raise RuntimeError("Use 'async with' or pass http_client")
        return self._owned_http_client

    # Core API
    async def complete(
        self,
        *,
        messages: Sequence[LlmChatMessage],
        tools: Sequence[Mapping[str, Any]],
        prompt_version: str | None = None,
    ) -> LlmCompletion:
        version = prompt_version or self._settings.agent_llm_prompt_version
        payload: dict[str, Any] = {
            "model": self._settings.agent_llm_model,
            "messages": [_message_to_provider(message) for message in messages],
        }
        if tools:
            payload["tools"] = list(tools)
        try:
            response = await self._http_client().post(
                f"{self._settings.agent_llm_base_url}/chat/completions",
                headers={
                    "Authorization": (
                        "Bearer "
                        f"{self._settings.agent_llm_api_key.get_secret_value()}"
                    ),
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as error:
            raise AgentLlmRequestError("LLM provider request failed") from error
        if response.status_code != 200:
            raise AgentLlmResponseError("LLM provider returned an error status")

        try:
            body = response.json()
        except json.JSONDecodeError as error:
            raise AgentLlmResponseError("LLM provider returned non-JSON") from error
        
        return _completion_from_provider(
            body,
            fallback_model=self._settings.agent_llm_model,
            prompt_version=version,
        )

# Example
# { "role": "system", "content": "Symbol: AAPL\nSession: ..." }
# { "role": "user", "content": "帮我加一条 PE 涨超 20% 的风险条件" }
# {
#   "role": "assistant",
#   "content": "我来创建这条条件。",
#   "tool_calls": [
#     {
#       "id": "call_abc123",
#       "type": "function",
#       "function": {
#         "name": "create_condition",
#         "arguments": "{\"name\":\"PE spike\",\"kind\":\"risk\",\"metric\":\"pe_ratio_change_percent\",\"operator\":\"greater_than\",\"threshold\":20}"
#       }
#     }
#   ]
# }
def _message_to_provider(message: LlmChatMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": message.role,
        "content": message.content,
    }
    if message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                },
            }
            for call in message.tool_calls
        ]
    return payload

def _completion_from_provider(
    body: object,
    *,
    fallback_model: str,
    prompt_version: str,
) -> LlmCompletion:
    if not isinstance(body, dict):
        raise AgentLlmResponseError("LLM provider body must be an object")

    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AgentLlmResponseError("LLM provider returned no choices")

    first = choices[0]
    if not isinstance(first, dict):
        raise AgentLlmResponseError("LLM provider choice is invalid")

    raw_message = first.get("message")
    if not isinstance(raw_message, dict):
        raise AgentLlmResponseError("LLM provider message is invalid")

    content = raw_message.get("content")
    if content is not None and not isinstance(content, str):
        raise AgentLlmResponseError("LLM provider content is invalid")

    if isinstance(content, str):
        content = content.strip() or None
    tool_calls = _parse_tool_calls(raw_message.get("tool_calls"))
    
    finish_reason = first.get("finish_reason")
    if not isinstance(finish_reason, str) or not finish_reason.strip():
        finish_reason = "stop" if not tool_calls else "tool_calls"

    model = body.get("model")
    if not isinstance(model, str) or not model.strip():
        model = fallback_model

    return LlmCompletion(
        content=content,
        tool_calls=tuple(tool_calls),
        model=model.strip()[:100],
        prompt_version=prompt_version,
        finish_reason=finish_reason.strip()[:50],
    )

def _parse_tool_calls(value: object) -> list[LlmToolCall]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AgentLlmResponseError("LLM provider tool_calls must be a list")
    parsed: list[LlmToolCall] = []
    for item in value:
        if not isinstance(item, dict):
            raise AgentLlmResponseError("LLM provider tool_call is invalid")
        call_id = item.get("id")
        function = item.get("function")
        if not isinstance(call_id, str) or not call_id.strip():
            raise AgentLlmResponseError("LLM provider tool_call id is invalid")
        if not isinstance(function, dict):
            raise AgentLlmResponseError("LLM provider tool_call function is invalid")
        name = function.get("name")
        raw_arguments = function.get("arguments")
        if not isinstance(name, str) or not name.strip():
            raise AgentLlmResponseError("LLM provider tool_call name is invalid")
        parsed.append(
            LlmToolCall(
                id=call_id.strip()[:100],
                name=name.strip()[:100],
                arguments=_parse_arguments(raw_arguments),
            )
        )
    return parsed

def _parse_arguments(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise AgentLlmResponseError("LLM tool arguments must be a JSON object")
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError as error:
        raise AgentLlmResponseError("LLM tool arguments are not valid JSON") from error
    if not isinstance(loaded, dict):
        raise AgentLlmResponseError("LLM tool arguments must be a JSON object")
    return loaded
