import unittest
from datetime import UTC, datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from app.domain.agent_models import (
    AgentConditionWrite,
    AgentConditionWriteAction,
    AgentMemory,
    AgentMessage,
    AgentMessageRole,
    AgentSession,
    AgentSessionStatus,
)

def _utc_now() -> datetime:
    return datetime.now(tz=UTC)

class AgentSessionTests(unittest.TestCase):
    def test_normalizes_symbol_and_defaults_to_open(self) -> None:
        session = AgentSession(
            user_id=uuid4(),
            thesis_id=uuid4(),
            symbol=" aapl ",
        )
        self.assertEqual(session.symbol, "AAPL")
        self.assertEqual(session.status, AgentSessionStatus.OPEN)

    def test_rejects_naive_datetime(self) -> None:
        with self.assertRaises(ValidationError):
            AgentSession(
                user_id=uuid4(),
                thesis_id=uuid4(),
                symbol="AAPL",
                created_at=datetime.now(),
            )

    def test_rejects_updated_at_before_created_at(self) -> None:
        created = datetime(2026, 1, 2, tzinfo=timezone.utc)
        updated = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with self.assertRaises(ValidationError):
            AgentSession(
                user_id=uuid4(),
                thesis_id=uuid4(),
                symbol="AAPL",
                created_at=created,
                updated_at=updated,
            )

    def test_is_frozen(self) -> None:
        session = AgentSession(user_id=uuid4(), thesis_id=uuid4(), symbol="AAPL")
        with self.assertRaises(ValidationError):
            session.status = AgentSessionStatus.CLOSED

class AgentMessageTests(unittest.TestCase):
    def test_user_message_forbids_tool_fields(self) -> None:
        with self.assertRaises(ValidationError):
            AgentMessage(
                session_id=uuid4(),
                user_id=uuid4(),
                role=AgentMessageRole.USER,
                content="Generate conditions",
                tool_name="create_condition",
                tool_call_id="call_1",
            )

    def test_assistant_message_forbids_tool_fields(self) -> None:
        with self.assertRaises(ValidationError):
            AgentMessage(
                session_id=uuid4(),
                user_id=uuid4(),
                role=AgentMessageRole.ASSISTANT,
                content="Generate conditions",
                tool_name="create_condition",
                tool_call_id="call_1",
            )

    def test_tool_message_requires_tool_identity(self) -> None:
        with self.assertRaises(ValidationError):
            AgentMessage(
                session_id=uuid4(),
                user_id=uuid4(),
                role=AgentMessageRole.TOOL,
                content="created condition",
            )

    def test_tool_message_accepts_tool_identity(self) -> None:
            message = AgentMessage(
                session_id=uuid4(),
                user_id=uuid4(),
                role=AgentMessageRole.TOOL,
                content="created condition abc",
                tool_name="create_condition",
                tool_call_id="call_1",
            )
            self.assertEqual(message.tool_name, "create_condition")

    def test_model_metadata_only_on_assistant(self) -> None:
        with self.assertRaises(ValidationError):
            AgentMessage(
                session_id=uuid4(),
                user_id=uuid4(),
                role=AgentMessageRole.USER,
                content="hello",
                model="gpt-4.1",
            )
class AgentMemoryTests(unittest.TestCase):
    def test_rejects_empty_summary(self) -> None:
        with self.assertRaises(ValidationError):
            AgentMemory(
                session_id=uuid4(),
                user_id=uuid4(),
                summary="   ",
                message_count_at_summary=3,
            )
class AgentConditionWriteTests(unittest.TestCase):
    def test_records_create_action(self) -> None:
        write = AgentConditionWrite(
            session_id=uuid4(),
            message_id=uuid4(),
            user_id=uuid4(),
            thesis_id=uuid4(),
            condition_id=uuid4(),
            action=AgentConditionWriteAction.CREATE,
        )
        self.assertEqual(write.action, AgentConditionWriteAction.CREATE)
        self.assertEqual(write.created_at.tzinfo, UTC)
