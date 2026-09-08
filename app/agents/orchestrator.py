"""Run the condition-authoring tool loop.

The orchestrator never validates metrics or writes conditions itself.
It persists messages, calls the LLM, then dispatches tools.
"""

from __future__ import annotations

import json
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.agents.context import AgentContextAssembler, render_context_pack
from app.agents.llm import AgentLlmClient, LlmChatMessage, LlmCompletion, LlmToolCall
from app.agents.tools import TOOL_DEFINITIONS, ConditionAuthorTools
from app.database.agent_repositories import AgentRepository
from app.database.thesis_repositories import InvalidAggregateError
from app.domain.agent_models import (
    AgentMessage,
    AgentMessageRole,
    AgentSessionStatus,
)

_MAX_ROUNDS_DEFAULT = 6
_CONTENT_LIMIT = 20000
_ASSISTANT_PLACEHOLDER = "I'll draft monitoring conditions with the available tools."
GENERATE_USER_PROMPT = (
    "Create deterministic monitoring conditions for the current thesis. "
    "Use only allowed metrics, kinds, and operators. Prefer risk and "
    "invalidation conditions the rule engine can evaluate. Call tools "
    "to persist them."
)
_SYSTEM_INSTRUCTIONS = (
    "You are the condition-authoring agent for Stock Master. "
    "Use tools to read the metric catalog and to create or update "
    "conditions. Never invent a metric name. Never compute prices, "
    "returns, or thresholds yourself. Never call evaluate or ingestion. "
    "thesis_id and user_id are assigned by the system."
)

class AgentStopReason:
    COMPLETED = "completed"
    MAX_ROUNDS = "max_rounds"

class AgentTurnResult(BaseModel):
    """Outcome of one generate or chat turn"""

    model_config = ConfigDict(frozen=True)

    assistant_text: str = Field(min_length=1, max_length=_CONTENT_LIMIT)
    round_count: int = Field(ge=1)
    stop_reason: str
    session_id: UUID

class ConditionAuthorOrchestrator:
    """Bound tool loop for one open agent session."""

    def __init__(
        self,
        *,
        assembler: AgentContextAssembler,
        tools: ConditionAuthorTools,
        llm: AgentLlmClient,
        agents: AgentRepository,
        max_rounds: int = _MAX_ROUNDS_DEFAULT,
    ) -> None:
        if max_rounds < 1:
            raise ValueError("max_rounds must be at least 1")
        self._assembler = assembler
        self._tools = tools
        self._llm = llm # Protocol
        self._agents = agents
        self._max_rounds = max_rounds

    # 'session_id' refers to the agent chat session, not the database connection session
    async def generate(self, *, user_id: UUID, session_id: UUID) -> AgentTurnResult:
        return await self._run_turn(
            user_id=user_id,
            session_id=session_id,
            user_text=GENERATE_USER_PROMPT,
        )

    async def chat(self, *, user_id: UUID, session_id: UUID, user_text: str) -> AgentTurnResult:
        stripped = user_text.strip()
        if not stripped:
            raise ValueError("user_text must be non-empty")
        return await self._run_turn(
            user_id=user_id,
            session_id=session_id,
            user_text=stripped,
        )
    
    async def _run_turn(self, *, user_id: UUID, session_id: UUID, user_text: str) -> AgentTurnResult:
        pack = await self._assembler.assemble(
            user_id=user_id,
            session_id=session_id,
        )
        session = pack.session
        if session.status is AgentSessionStatus.CLOSED:
            raise InvalidAggregateError("Cannot run the agent on a closed session")

        await self._agents.append_message(
            AgentMessage(
                session_id=session_id,
                user_id=user_id,
                role=AgentMessageRole.USER,
                content=_clip(user_text)
            )
        )

        llm_messages = [
            LlmChatMessage(
                role="system",
                content=_clip(_SYSTEM_INSTRUCTIONS + "\n\n" + render_context_pack(pack))
            ),
            LlmChatMessage(role='user', content=_clip(user_text)),
        ]

        last_text = _ASSISTANT_PLACEHOLDER
        rounds = 0
        stop_reason = AgentStopReason.MAX_ROUNDS

        for rounds in range(1, self._max_rounds + 1):
            completion = await self._llm.complete(
                messages=llm_messages,
                tools=TOOL_DEFINITIONS,
            )
            last_text = _assistant_text(completion)
            await self._agents.append_message(
                AgentMessage(
                    session_id=session_id,
                    user_id=user_id,
                    role=AgentMessageRole.ASSISTANT,
                    content=last_text,
                    model= completion.model,
                    prompt_version=completion.prompt_version,
                )
            )
            llm_messages.append(
                LlmChatMessage(
                    role="assistant",
                    content=last_text,
                    tool_calls=completion.tool_calls,
                )
            )
            if not completion.tool_calls:
                stop_reason = AgentStopReason.COMPLETED
                break

            for tool_call in completion.tool_calls:
                tool_message = await self._agents.append_message(
                    AgentMessage(
                        session_id=session.id,
                        user_id=user_id,
                        role=AgentMessageRole.TOOL,
                        content=_clip(_invocation_content(tool_call)),
                        tool_name=tool_call.name,
                        tool_call_id=tool_call.id,
                    )
                )
                result = await self._tools.execute(
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments,
                    user_id=user_id,
                    session=session,
                    message_id=tool_message.id,
                )
                llm_messages.append(
                    LlmChatMessage(
                        role="tool",
                        content=_clip(result.model_dump_json()),
                        tool_call_id=tool_call.id,
                    )
                )

        return AgentTurnResult(
            assistant_text=last_text,
            round_count=rounds,
            stop_reason=stop_reason,
            session_id=session.id
        )

def _assistant_text(completion: LlmCompletion) -> str:
    if completion.content:
        return _clip(completion.content)
    if completion.tool_calls:
        return _ASSISTANT_PLACEHOLDER
    return "I could not draft conditions from the current thesis."

def _invocation_content(call: LlmToolCall) -> str:
    return json.dumps(
        {"name": call.name, "arguments": call.arguments},
        default=str,
    )

def _clip(value: str) -> str:
    if len(value) <= _CONTENT_LIMIT:
        return value
    return value[: _CONTENT_LIMIT - 3] + "..."