from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Self

import httpx

from app.agents.llm.errors import (
    AgentLlmConfigError,
    AgentLlmRequestError,
    AgentLlmResponseError,
)
from app.agents.llm.settings import AgentLlmSettings, get_agent_llm_settings
from app.agents.llm.types import LlmChatMessage, LlmCompletion, LlmToolCall

_CLIENT_USER_AGENT = "stock-master-bot/0.1"


class OpenAICompatibleLlmClient:
    """POST /chat/completions against an allowlisted OpenAI-compatible host."""

    def __init__(
        self,
        settings: AgentLlmSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_agent_llm_settings()
        if not self._settings.resolved_api_key():
            raise AgentLlmConfigError("LLM API key is required")
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

    async def complete(
        self,
        *,
        messages: Sequence[LlmChatMessage],
        tools: Sequence[Mapping[str, Any]],
        prompt_version: str | None = None,
    ) -> LlmCompletion:
        version = prompt_version or self._settings.agent_llm_prompt_version
        payload: dict[str, Any] = {
            "model": self._settings.model,
            "messages": [_message_to_provider(message) for message in messages],
            "max_tokens": self._settings.agent_llm_max_tokens,
        }
        if tools:
            payload["tools"] = list(tools)
        try:
            response = await self._http_client().post(
                f"{self._settings.base_url}/chat/completions",
                headers={
                    "Authorization": (
                        f"Bearer {self._settings.resolved_api_key()}"
                    ),
                    "Content-Type": "application/json",
                    "User-Agent": _CLIENT_USER_AGENT,
                    "Accept": "application/json",
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
            fallback_model=self._settings.model,
            prompt_version=version,
        )


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
