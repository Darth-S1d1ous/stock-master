import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.database.agent_repositories import AgentRepository
from app.domain.agent_models import AgentMessageRole, AgentSessionStatus


class AgentRepositoryMappingTests(unittest.TestCase):
    def test_session_row_maps_to_domain(self) -> None:
        user_id = uuid4()
        thesis_id = uuid4()
        session_id = uuid4()
        created = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
        row = SimpleNamespace(
            id=session_id,
            user_id=user_id,
            thesis_id=thesis_id,
            symbol="AAPL",
            status="open",
            created_at=created,
            updated_at=created,
        )

        session = AgentRepository._session_from_row(row)  # type: ignore[arg-type]

        self.assertEqual(session.id, session_id)
        self.assertEqual(session.status, AgentSessionStatus.OPEN)
        self.assertEqual(session.symbol, "AAPL")

    def test_tool_message_row_maps_tool_fields(self) -> None:
        created = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
        row = SimpleNamespace(
            id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            role="tool",
            content="created condition",
            tool_name="create_condition",
            tool_call_id="call_1",
            model=None,
            prompt_version=None,
            created_at=created,
        )

        message = AgentRepository._message_from_row(row)  # type: ignore[arg-type]
        self.assertEqual(message.role, AgentMessageRole.TOOL)
        self.assertEqual(message.tool_name, "create_condition")

    def test_pagination_rejects_invalid_limits(self) -> None:
        with self.assertRaises(ValueError):
            AgentRepository._validate_pagination(limit=0, offset=0)
        with self.assertRaises(ValueError):
            AgentRepository._validate_pagination(limit=10, offset=-1)