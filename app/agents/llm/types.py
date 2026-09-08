from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
