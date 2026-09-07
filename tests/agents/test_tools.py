import unittest
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

from pydantic import ValidationError

from app.agents.tools import (
    TOOL_DEFINITIONS,
    ConditionAuthorTools,
    CreateConditionToolArgs,
    ToolErrorCode,
)
from app.database.agent_repositories import AgentRepository
from app.database.thesis_repositories import ResourceNotFoundError, ThesisRepository
from app.domain.agent_models import AgentSession
from app.domain.thesis_models import (
    ComparisonOperator,
    ConditionKind,
    MetricCode,
    ThesisCondition,
)

_NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


class CreateConditionToolArgsTests(unittest.TestCase):
    def test_rejects_unknown_metric(self) -> None:
        with self.assertRaises(ValidationError):
            CreateConditionToolArgs.model_validate(
                {
                    "name": "Fake",
                    "kind": "risk",
                    "metric": "services_revenue_growth",
                    "operator": "less_than",
                    "threshold": -5,
                }
            )


class ConditionAuthorToolsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.user_id = uuid4()
        self.other_user_id = uuid4()
        self.message_id = uuid4()
        self.session = AgentSession(
            user_id=self.user_id,
            thesis_id=uuid4(),
            symbol="AAPL",
            created_at=_NOW,
            updated_at=_NOW,
        )
        self.condition = ThesisCondition(
            thesis_id=self.session.thesis_id,
            user_id=self.user_id,
            name="PE spike",
            kind=ConditionKind.RISK,
            metric=MetricCode.PE_RATIO_CHANGE_PERCENT,
            operator=ComparisonOperator.GREATER_THAN,
            threshold=Decimal(20),
            created_at=_NOW,
            updated_at=_NOW,
        )
        self.thesis_mock = AsyncMock(spec=ThesisRepository)
        self.agent_mock = AsyncMock(spec=AgentRepository)
        self.tools = ConditionAuthorTools(
            theses=cast(ThesisRepository, self.thesis_mock),
            agents=cast(AgentRepository, self.agent_mock),
        )

    async def test_unknown_metric_does_not_write(self) -> None:
        result = await self.tools.execute(
            tool_name="create_condition",
            arguments={
                "name": "Fake",
                "kind": "risk",
                "metric": "services_revenue_growth",
                "operator": "less_than",
                "threshold": -5,
            },
            user_id=self.user_id,
            session=self.session,
            message_id=self.message_id,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, ToolErrorCode.INVALID_ARGUMENTS)
        self.thesis_mock.create_condition.assert_not_awaited()
        self.agent_mock.record_condition_write.assert_not_awaited()

    async def test_create_binds_thesis_from_session_not_arguments(self) -> None:
        self.thesis_mock.create_condition.side_effect = lambda condition: condition

        result = await self.tools.execute(
            tool_name="create_condition",
            arguments={
                "name": "PE spike",
                "kind": "risk",
                "metric": "pe_ratio_change_percent",
                "operator": "greater_than",
                "threshold": 20,
                "thesis_id": str(uuid4()),
            },
            user_id=self.user_id,
            session=self.session,
            message_id=self.message_id,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, ToolErrorCode.INVALID_ARGUMENTS)
        self.thesis_mock.create_condition.assert_not_awaited()

        result = await self.tools.execute(
            tool_name="create_condition",
            arguments={
                "name": "PE spike",
                "kind": "risk",
                "metric": "pe_ratio_change_percent",
                "operator": "greater_than",
                "threshold": 20,
            },
            user_id=self.user_id,
            session=self.session,
            message_id=self.message_id,
        )

        self.assertTrue(result.ok)
        created = self.thesis_mock.create_condition.await_args.args[0]
        self.assertEqual(created.thesis_id, self.session.thesis_id)
        self.assertEqual(created.user_id, self.user_id)
        self.assertEqual(created.metric, MetricCode.PE_RATIO_CHANGE_PERCENT)
        write = self.agent_mock.record_condition_write.await_args.args[0]
        self.assertEqual(write.message_id, self.message_id)
        self.assertEqual(write.action.value, "create")

    async def test_update_uses_session_thesis_so_foreign_ids_are_not_found(
        self,
    ) -> None:
        self.thesis_mock.update_condition.side_effect = ResourceNotFoundError(
            "Thesis condition was not found"
        )

        result = await self.tools.execute(
            tool_name="update_condition",
            arguments={
                "condition_id": str(uuid4()),
                "expected_version": 1,
                "threshold": 10,
            },
            user_id=self.user_id,
            session=self.session,
            message_id=self.message_id,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, ToolErrorCode.NOT_FOUND)
        kwargs = self.thesis_mock.update_condition.await_args.kwargs
        self.assertEqual(kwargs["thesis_id"], self.session.thesis_id)
        self.assertEqual(kwargs["user_id"], self.user_id)
        self.agent_mock.record_condition_write.assert_not_awaited()

    async def test_catalog_tool_matches_definitions(self) -> None:
        result = await self.tools.execute(
            tool_name="list_metric_catalog",
            arguments={},
            user_id=self.user_id,
            session=self.session,
        )
        names = [item["function"]["name"] for item in TOOL_DEFINITIONS]

        self.assertTrue(result.ok)
        self.assertIsNotNone(result.data)
        metrics = cast(dict[str, Any], result.data)["metrics"]
        self.assertEqual(len(metrics), len(MetricCode))
        self.assertEqual(
            names,
            [
                "list_metric_catalog",
                "list_thesis_conditions",
                "create_condition",
                "update_condition",
            ],
        )

    async def test_foreign_session_is_forbidden(self) -> None:
        result = await self.tools.execute(
            tool_name="list_thesis_conditions",
            arguments={},
            user_id=self.other_user_id,
            session=self.session,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, ToolErrorCode.FORBIDDEN)
        self.thesis_mock.list_conditions.assert_not_awaited()