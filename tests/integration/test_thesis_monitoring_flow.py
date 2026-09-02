from datetime import UTC, date, datetime
from decimal import Decimal
import os
from pathlib import Path
import unittest
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.data_sources.models import DailyBar
from app.database.domain_tables import (
    DomainEventTable,
    EventEvidenceTable,
    RuleEvaluationTable,
)
from app.database.repositories import StockDataRepository
from app.database.settings import DatabaseSettings, get_database_settings
from app.database.thesis_repositories import ThesisRepository
from app.domain.thesis_models import (
    ComparisonOperator,
    ConditionKind,
    InvestmentThesis,
    MetricCode,
    ThesisCondition,
)
from app.services.thesis_monitoring_service import ThesisMonitoringService


_RUN_INTEGRATION = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)

pytestmark = pytest.mark.integration


@unittest.skipUnless(
    _RUN_INTEGRATION,
    "set RUN_POSTGRES_INTEGRATION=1 to run PostgreSQL integration tests",
)
class ThesisMonitoringFlowIntegrationTests(
    unittest.IsolatedAsyncioTestCase
):
    settings: DatabaseSettings
    engine: AsyncEngine
    connection: AsyncConnection
    session: AsyncSession

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.settings = get_database_settings()
        if not cls.settings.postgres_db.lower().endswith("_test"):
            raise RuntimeError(
                "PostgreSQL integration tests require a database name ending in '_test'"
            )
        if cls.settings.postgres_host not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise unittest.SkipTest(
                "integration tests only run against a local PostgreSQL host"
            )

        config = Config(str(_PROJECT_ROOT / "alembic.ini"))
        command.upgrade(config, "head")

    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine(
            self.settings.async_database_url,
            poolclass=NullPool,
            connect_args={
                "timeout": 10,
                "server_settings": {
                    "application_name": (
                        "stock-master-bot-integration-tests"
                    ),
                },
            },
        )
        self.connection = await self.engine.connect()
        await self.connection.begin()
        self.session = AsyncSession(
            bind=self.connection,
            autoflush=False,
            expire_on_commit=False,
        )

    async def asyncTearDown(self) -> None:
        await self.session.close()
        if self.connection.in_transaction():
            await self.connection.rollback()
        await self.connection.close()
        await self.engine.dispose()

    async def test_monitoring_flow_is_auditable_idempotent_and_owned(
        self,
    ) -> None:
        user_id = uuid4()
        other_user_id = uuid4()
        thesis = InvestmentThesis(
            user_id=user_id,
            symbol="AAPL",
            title="Apple downside risk",
            description="Alert on a material daily decline.",
            created_at=_NOW,
            updated_at=_NOW,
        )
        condition = ThesisCondition(
            thesis_id=thesis.id,
            user_id=user_id,
            name="Daily decline",
            kind=ConditionKind.RISK,
            metric=MetricCode.DAILY_PRICE_CHANGE_PERCENT,
            operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            threshold=Decimal("-5"),
            created_at=_NOW,
            updated_at=_NOW,
        )

        stock_repository = StockDataRepository(self.session)
        thesis_repository = ThesisRepository(self.session)
        service = ThesisMonitoringService(
            stock_data_repo=stock_repository,
            thesis_repo=thesis_repository,
            clock=lambda: _NOW,
        )

        await thesis_repository.create_thesis(thesis)
        await thesis_repository.create_condition(condition)
        await stock_repository.save_daily_bars(
            [
                self._daily_bar(
                    trading_date=date(2026, 8, 25),
                    close="100",
                ),
                self._daily_bar(
                    trading_date=date(2026, 8, 26),
                    close="94",
                ),
            ]
        )

        first_result = await service.evaluate_thesis(
            user_id=user_id,
            thesis_id=thesis.id,
            source="alpha_vantage",
        )
        second_result = await service.evaluate_thesis(
            user_id=user_id,
            thesis_id=thesis.id,
            source="alpha_vantage",
        )

        self.assertEqual(first_result.evaluation_count, 1)
        self.assertEqual(first_result.matched_count, 1)
        self.assertEqual(first_result.event_count, 1)
        self.assertEqual(second_result.evaluation_count, 1)
        self.assertEqual(second_result.event_count, 1)

        first_condition_result = first_result.conditions[0]
        second_condition_result = second_result.conditions[0]
        self.assertEqual(
            first_condition_result.evaluation.id,
            second_condition_result.evaluation.id,
        )
        self.assertIsNotNone(first_condition_result.event)
        self.assertIsNotNone(second_condition_result.event)
        self.assertEqual(
            first_condition_result.event.id,
            second_condition_result.event.id,
        )
        self.assertEqual(len(first_condition_result.evidence), 2)
        self.assertEqual(len(second_condition_result.evidence), 2)
        self.assertEqual(
            {
                evidence.source_record_id
                for evidence in first_condition_result.evidence
            },
            set(first_condition_result.evaluation.observation_ids),
        )

        evaluation_count = await self.session.scalar(
            select(func.count())
            .select_from(RuleEvaluationTable)
            .where(
                RuleEvaluationTable.user_id == user_id,
                RuleEvaluationTable.thesis_id == thesis.id,
            )
        )
        event_count = await self.session.scalar(
            select(func.count())
            .select_from(DomainEventTable)
            .where(
                DomainEventTable.user_id == user_id,
                DomainEventTable.thesis_id == thesis.id,
            )
        )
        evidence_count = await self.session.scalar(
            select(func.count())
            .select_from(EventEvidenceTable)
            .where(EventEvidenceTable.user_id == user_id)
        )

        self.assertEqual(evaluation_count, 1)
        self.assertEqual(event_count, 1)
        self.assertEqual(evidence_count, 2)

        self.assertIsNone(
            await thesis_repository.get_thesis(
                user_id=other_user_id,
                thesis_id=thesis.id,
            )
        )
        self.assertIsNone(
            await thesis_repository.get_rule_evaluation(
                user_id=other_user_id,
                evaluation_id=first_condition_result.evaluation.id,
            )
        )
        self.assertIsNone(
            await thesis_repository.get_event(
                user_id=other_user_id,
                event_id=first_condition_result.event.id,
            )
        )

    @staticmethod
    def _daily_bar(
        *,
        trading_date: date,
        close: str,
    ) -> DailyBar:
        close_value = Decimal(close)
        return DailyBar(
            symbol="AAPL",
            trading_date=trading_date,
            open=close_value,
            high=close_value,
            low=close_value,
            close=close_value,
            volume=1_000,
            source="alpha_vantage",
            received_at=_NOW,
        )


if __name__ == "__main__":
    unittest.main()
