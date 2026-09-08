import unittest
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

from app.agents.context import AgentContextAssembler, AgentContextPack, build_metric_catalog
from app.agents.llm import LlmChatMessage, LlmCompletion, LlmToolCall
from app.agents.orchestrator import (
    GENERATE_USER_PROMPT,
    AgentStopReason,
    ConditionAuthorOrchestrator,
)
from app.agents.tools import TOOL_DEFINITIONS, ConditionAuthorTools, ToolResult
from app.database.agent_repositories import AgentRepository
from app.database.thesis_repositories import InvalidAggregateError
from app.domain.agent_models import AgentMessage, AgentMessageRole, AgentSession, AgentSessionStatus
from app.domain.thesis_models import ComparisonOperator, ConditionKind, InvestmentThesis

_NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def _completion(
    *,
    content: str | None = None,
    tool_calls: tuple[LlmToolCall, ...] = (),
    finish_reason: str = "stop",
) -> LlmCompletion:
    return LlmCompletion(
        content=content,
        tool_calls=tool_calls,
        model="fake-model",
        prompt_version="condition-author-v1",
        finish_reason=finish_reason,
    )


class ScriptedLlm:
    """Deterministic AgentLlmClient: returns queued completions, records calls."""

    def __init__(self, completions: Sequence[LlmCompletion]) -> None:
        self._completions = list(completions)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        messages: Sequence[LlmChatMessage],
        tools: Sequence[Mapping[str, Any]],
        prompt_version: str | None = None,
    ) -> LlmCompletion:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools),
                "prompt_version": prompt_version,
            }
        )
        if not self._completions:
            raise AssertionError("LLM was called more times than scripted")
        return self._completions.pop(0)


class ConditionAuthorOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.user_id = uuid4()
        self.thesis = InvestmentThesis(
            user_id=self.user_id,
            symbol="AAPL",
            title="Services growth",
            description="Services remain the primary growth driver.",
            created_at=_NOW,
            updated_at=_NOW,
        )
        self.session = AgentSession(
            user_id=self.user_id,
            thesis_id=self.thesis.id,
            symbol="AAPL",
            created_at=_NOW,
            updated_at=_NOW,
        )
        self.pack = AgentContextPack(
            session=self.session,
            current_thesis=self.thesis,
            related_theses=(),
            metric_catalog=build_metric_catalog(),
            allowed_kinds=tuple(ConditionKind),
            allowed_operators=tuple(ComparisonOperator),
            messages=(),
            memory=None,
            condition_writes=(),
        )
        self.assembler = AsyncMock(spec=AgentContextAssembler)
        self.assembler.assemble.return_value = self.pack
        self.tools = AsyncMock(spec=ConditionAuthorTools)
        self.tools.execute.return_value = ToolResult(
            ok=True,
            tool_name="list_metric_catalog",
            data={"metrics": []},
        )
        self.agents = AsyncMock(spec=AgentRepository)
        self.agents.append_message.side_effect = lambda message: message

    def _orchestrator(
        self,
        llm: ScriptedLlm,
        *,
        max_rounds: int = 6,
    ) -> ConditionAuthorOrchestrator:
        return ConditionAuthorOrchestrator(
            assembler=cast(AgentContextAssembler, self.assembler),
            tools=cast(ConditionAuthorTools, self.tools),
            llm=llm,
            agents=cast(AgentRepository, self.agents),
            max_rounds=max_rounds,
        )

    def test_rejects_non_positive_max_rounds(self) -> None:
        with self.assertRaises(ValueError):
            self._orchestrator(ScriptedLlm([]), max_rounds=0)

    async def test_generate_runs_tool_then_completes(self) -> None:
        llm = ScriptedLlm(
            [
                _completion(
                    tool_calls=(
                        LlmToolCall(
                            id="call_1",
                            name="list_metric_catalog",
                            arguments={},
                        ),
                    ),
                    finish_reason="tool_calls",
                ),
                _completion(content="Drafted conditions from the catalog."),
            ]
        )
        orchestrator = self._orchestrator(llm)

        result = await orchestrator.generate(
            user_id=self.user_id,
            session_id=self.session.id,
        )

        self.assertEqual(result.assistant_text, "Drafted conditions from the catalog.")
        self.assertEqual(result.round_count, 2)
        self.assertEqual(result.stop_reason, AgentStopReason.COMPLETED)
        self.assertEqual(result.session_id, self.session.id)
        self.assembler.assemble.assert_awaited_once_with(
            user_id=self.user_id,
            session_id=self.session.id,
        )
        self.assertEqual(len(llm.calls), 2)
        self.assertEqual(llm.calls[0]["tools"], list(TOOL_DEFINITIONS))
        self.assertEqual(llm.calls[0]["messages"][1].content, GENERATE_USER_PROMPT)
        self.assertEqual(llm.calls[1]["messages"][-1].role, "tool")
        self.assertEqual(llm.calls[1]["messages"][-1].tool_call_id, "call_1")

        persisted = [call.args[0] for call in self.agents.append_message.await_args_list]
        self.assertEqual(
            [message.role for message in persisted],
            [
                AgentMessageRole.USER,
                AgentMessageRole.ASSISTANT,
                AgentMessageRole.TOOL,
                AgentMessageRole.ASSISTANT,
            ],
        )
        self.assertEqual(persisted[0].content, GENERATE_USER_PROMPT)
        self.assertEqual(persisted[1].model, "fake-model")
        self.assertEqual(persisted[1].prompt_version, "condition-author-v1")
        self.assertEqual(persisted[2].tool_name, "list_metric_catalog")
        self.assertEqual(persisted[2].tool_call_id, "call_1")
        self.assertEqual(persisted[3].content, "Drafted conditions from the catalog.")
        self.tools.execute.assert_awaited_once()
        kwargs = self.tools.execute.await_args.kwargs
        self.assertEqual(kwargs["tool_name"], "list_metric_catalog")
        self.assertEqual(kwargs["arguments"], {})
        self.assertEqual(kwargs["user_id"], self.user_id)
        self.assertEqual(kwargs["session"], self.session)
        self.assertEqual(kwargs["message_id"], persisted[2].id)

    async def test_chat_persists_user_text_and_stops_without_tools(self) -> None:
        llm = ScriptedLlm([_completion(content="No new conditions needed.")])
        orchestrator = self._orchestrator(llm)

        result = await orchestrator.chat(
            user_id=self.user_id,
            session_id=self.session.id,
            user_text="  keep the PE spike  ",
        )

        self.assertEqual(result.assistant_text, "No new conditions needed.")
        self.assertEqual(result.round_count, 1)
        self.assertEqual(result.stop_reason, AgentStopReason.COMPLETED)
        persisted = self.agents.append_message.await_args_list[0].args[0]
        self.assertEqual(persisted.role, AgentMessageRole.USER)
        self.assertEqual(persisted.content, "keep the PE spike")
        self.tools.execute.assert_not_awaited()

    async def test_chat_rejects_blank_user_text(self) -> None:
        orchestrator = self._orchestrator(ScriptedLlm([]))

        with self.assertRaises(ValueError):
            await orchestrator.chat(
                user_id=self.user_id,
                session_id=self.session.id,
                user_text="   ",
            )

        self.assembler.assemble.assert_not_awaited()
        self.agents.append_message.assert_not_awaited()

    async def test_closed_session_does_not_call_llm_or_persist(self) -> None:
        closed = self.session.model_copy(update={"status": AgentSessionStatus.CLOSED})
        self.assembler.assemble.return_value = self.pack.model_copy(update={"session": closed})
        llm = ScriptedLlm([_completion(content="should not run")])
        orchestrator = self._orchestrator(llm)

        with self.assertRaises(InvalidAggregateError):
            await orchestrator.generate(
                user_id=self.user_id,
                session_id=self.session.id,
            )

        self.assertEqual(llm.calls, [])
        self.agents.append_message.assert_not_awaited()
        self.tools.execute.assert_not_awaited()

    async def test_max_rounds_stops_while_model_keeps_calling_tools(self) -> None:
        tool_call = LlmToolCall(
            id="call_loop",
            name="list_metric_catalog",
            arguments={},
        )
        llm = ScriptedLlm(
            [
                _completion(tool_calls=(tool_call,), finish_reason="tool_calls"),
                _completion(tool_calls=(tool_call,), finish_reason="tool_calls"),
            ]
        )
        orchestrator = self._orchestrator(llm, max_rounds=2)

        result = await orchestrator.chat(
            user_id=self.user_id,
            session_id=self.session.id,
            user_text="keep going",
        )

        self.assertEqual(result.stop_reason, AgentStopReason.MAX_ROUNDS)
        self.assertEqual(result.round_count, 2)
        self.assertEqual(len(llm.calls), 2)
        self.assertEqual(self.tools.execute.await_count, 2)
        roles = [
            call.args[0].role for call in self.agents.append_message.await_args_list
        ]
        self.assertEqual(
            roles,
            [
                AgentMessageRole.USER,
                AgentMessageRole.ASSISTANT,
                AgentMessageRole.TOOL,
                AgentMessageRole.ASSISTANT,
                AgentMessageRole.TOOL,
            ],
        )
        self.assertIsInstance(
            self.agents.append_message.await_args_list[0].args[0],
            AgentMessage,
        )
