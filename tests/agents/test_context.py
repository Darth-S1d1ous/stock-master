import unittest
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

from app.agents.context import (
    AgentContextAssembler,
    build_metric_catalog,
    render_context_pack,
)
from app.database.agent_repositories import AgentRepository
from app.database.thesis_repositories import ThesisRepository
from app.domain.agent_models import (
    AgentMemory,
    AgentMessage,
    AgentMessageRole,
    AgentSession,
)
from app.domain.metric_registry import METRIC_REGISTRY
from app.domain.thesis_models import (
    ComparisonOperator,
    ConditionKind,
    InvestmentThesis,
    MetricCode,
    ThesisCondition,
)

_NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


class MetricCatalogTests(unittest.TestCase):
    def test_catalog_covers_every_registered_metric_and_nothing_else(self) -> None:
        catalog = build_metric_catalog()
        catalog_metrics = {entry.metric for entry in catalog}

        self.assertEqual(catalog_metrics, set(MetricCode))
        self.assertEqual(len(catalog), len(METRIC_REGISTRY))
        for entry in catalog:
            definition = METRIC_REGISTRY[entry.metric]
            self.assertEqual(entry.input_kind, definition.input_kind)
            self.assertEqual(
                entry.required_observations,
                definition.required_observations,
            )


class AgentContextAssemblerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.user_id = uuid4()
        self.other_user_id = uuid4()
        self.thesis = InvestmentThesis(
            user_id=self.user_id,
            symbol="AAPL",
            title="Services growth",
            description="Services remain the primary growth driver.",
            created_at=_NOW,
            updated_at=_NOW,
        )
        self.older_thesis = InvestmentThesis(
            user_id=self.user_id,
            symbol="AAPL",
            title="Older services view",
            description="Archived rationale.",
            created_at=_NOW,
            updated_at=_NOW,
        )
        self.condition = ThesisCondition(
            thesis_id=self.thesis.id,
            user_id=self.user_id,
            name="PE spike",
            kind=ConditionKind.RISK,
            metric=MetricCode.PE_RATIO_CHANGE_PERCENT,
            operator=ComparisonOperator.GREATER_THAN,
            threshold=Decimal(20),
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
        self.message = AgentMessage(
            session_id=self.session.id,
            user_id=self.user_id,
            role=AgentMessageRole.USER,
            content="Generate monitoring conditions.",
            created_at=_NOW,
        )
        self.memory = AgentMemory(
            session_id=self.session.id,
            user_id=self.user_id,
            summary="User wants invalidation on valuation stretch.",
            message_count_at_summary=1,
            updated_at=_NOW,
        )
        self.thesis_mock = AsyncMock(spec=ThesisRepository)
        self.agent_mock = AsyncMock(spec=AgentRepository)
        self.assembler = AgentContextAssembler(
            theses=cast(ThesisRepository, self.thesis_mock),
            agents=cast(AgentRepository, self.agent_mock),
        )

    async def test_assemble_loads_owned_symbol_history_and_session_memory(
        self,
    ) -> None:
        self.agent_mock.require_session.return_value = self.session
        self.thesis_mock.require_thesis.return_value = self.thesis
        self.thesis_mock.list_theses.return_value = [
            self.thesis,
            self.older_thesis,
        ]
        self.thesis_mock.list_conditions.side_effect = (
            lambda user_id, thesis_id, **kwargs: (
                [self.condition] if thesis_id == self.thesis.id else []
            )
        )
        self.agent_mock.list_messages.return_value = [self.message]
        self.agent_mock.get_memory.return_value = self.memory
        self.agent_mock.list_condition_writes.return_value = []

        pack = await self.assembler.assemble(
            user_id=self.user_id,
            session_id=self.session.id,
        )
        rendered = render_context_pack(pack)

        self.agent_mock.require_session.assert_awaited_once_with(
            user_id=self.user_id,
            session_id=self.session.id,
        )
        self.thesis_mock.require_thesis.assert_awaited_once_with(
            user_id=self.user_id,
            thesis_id=self.thesis.id,
        )
        self.thesis_mock.list_theses.assert_awaited_once_with(
            self.user_id,
            symbol="AAPL",
        )
        self.assertNotIn(str(self.other_user_id), str(self.thesis_mock.mock_calls))
        self.assertEqual(pack.current_thesis.id, self.thesis.id)
        self.assertEqual(len(pack.related_theses), 2)
        self.assertEqual(pack.memory, self.memory)
        self.assertIn("pe_ratio_change_percent", rendered)
        self.assertIn("Services remain the primary growth driver.", rendered)
        self.assertIn("User wants invalidation on valuation stretch.", rendered)
        self.assertNotIn("made_up_metric", rendered)
        for metric in MetricCode:
            self.assertIn(metric.value, rendered)