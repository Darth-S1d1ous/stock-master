from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
import unittest
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from app.data_sources.models import DailyBar, PriceAdjustment
from app.database.repositories import StockDataRepository
from app.database.thesis_repositories import ThesisRepository
from app.domain.event_models import EventSeverity
from app.domain.thesis_models import (
    ComparisonOperator,
    ConditionKind,
    InvestmentThesis,
    MetricCode,
    ThesisCondition,
    ThesisStatus,
)
from app.services.thesis_monitoring_service import (
    ThesisMonitoringService,
    ThesisNotMonitorableError,
)


_NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


class ThesisMonitoringServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.user_id = uuid4()
        self.thesis = InvestmentThesis(
            user_id=self.user_id,
            symbol="AAPL",
            title="Apple price risk",
            description="Monitor material daily price declines.",
            created_at=_NOW,
            updated_at=_NOW,
        )
        self.condition = ThesisCondition(
            thesis_id=self.thesis.id,
            user_id=self.user_id,
            name="Daily decline",
            kind=ConditionKind.RISK,
            metric=MetricCode.DAILY_PRICE_CHANGE_PERCENT,
            operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            threshold=Decimal("-5"),
            created_at=_NOW,
            updated_at=_NOW,
        )
        self.stock_repository_mock = AsyncMock(spec=StockDataRepository)
        self.thesis_repository_mock = AsyncMock(spec=ThesisRepository)
        self.stock_repository = cast(
            StockDataRepository,
            self.stock_repository_mock,
        )
        self.thesis_repository = cast(
            ThesisRepository,
            self.thesis_repository_mock,
        )
        self.service = ThesisMonitoringService(
            stock_data_repo=self.stock_repository,
            thesis_repo=self.thesis_repository,
            clock=lambda: _NOW,
        )

    async def test_matched_daily_condition_creates_event_and_evidence(
        self,
    ) -> None:
        bars = self._daily_bars(previous_close="100", current_close="94")
        self._configure_thesis(conditions=[self.condition])
        self.stock_repository_mock.get_recent_daily_bars.return_value = bars
        self.thesis_repository_mock.list_prior_evaluations.return_value = []
        self.thesis_repository_mock.save_rule_evaluation.side_effect = (
            lambda evaluation: evaluation
        )

        async def save_event(event, evidence):
            return event, list(evidence)

        self.thesis_repository_mock.save_event_with_evidence.side_effect = (
            save_event
        )

        result = await self.service.evaluate_thesis(
            user_id=self.user_id,
            thesis_id=self.thesis.id,
            source=" Alpha_Vantage ",
        )

        self.assertEqual(result.source, "alpha_vantage")
        self.assertEqual(result.evaluation_count, 1)
        self.assertEqual(result.matched_count, 1)
        self.assertEqual(result.event_count, 1)

        condition_result = result.conditions[0]
        self.assertEqual(
            condition_result.metric_result.value,
            Decimal("-6.00"),
        )
        self.assertTrue(condition_result.evaluation.matched)
        self.assertIsNotNone(condition_result.event)
        self.assertEqual(
            condition_result.event.severity,
            EventSeverity.WARNING,
        )
        self.assertEqual(len(condition_result.evidence), 2)
        self.assertEqual(
            {item.source_record_id for item in condition_result.evidence},
            {bar.observation_id for bar in bars},
        )

        self.stock_repository_mock.get_recent_daily_bars.assert_awaited_once_with(
            symbol="AAPL",
            source="alpha_vantage",
            adjustment=PriceAdjustment.RAW,
            limit=2,
        )
        self.stock_repository_mock.get_company_fundamentals_history.assert_not_awaited()
        self.thesis_repository_mock.save_rule_evaluation.assert_awaited_once()
        self.thesis_repository_mock.save_event_with_evidence.assert_awaited_once()

    async def test_unmatched_condition_persists_evaluation_without_event(
        self,
    ) -> None:
        self._configure_thesis(conditions=[self.condition])
        self.stock_repository_mock.get_recent_daily_bars.return_value = (
            self._daily_bars(previous_close="100", current_close="99")
        )
        self.thesis_repository_mock.save_rule_evaluation.side_effect = (
            lambda evaluation: evaluation
        )

        result = await self.service.evaluate_thesis(
            user_id=self.user_id,
            thesis_id=self.thesis.id,
            source="alpha_vantage",
        )

        self.assertEqual(result.evaluation_count, 1)
        self.assertEqual(result.matched_count, 0)
        self.assertEqual(result.event_count, 0)
        self.assertFalse(result.conditions[0].evaluation.matched)
        self.assertEqual(result.conditions[0].evidence, ())
        self.thesis_repository_mock.save_rule_evaluation.assert_awaited_once()
        self.thesis_repository_mock.save_event_with_evidence.assert_not_awaited()

    async def test_no_enabled_conditions_does_not_query_market_data(
        self,
    ) -> None:
        self._configure_thesis(conditions=[])

        result = await self.service.evaluate_thesis(
            user_id=self.user_id,
            thesis_id=self.thesis.id,
            source="alpha_vantage",
        )

        self.assertEqual(result.evaluation_count, 0)
        self.assertEqual(result.conditions, ())
        self.stock_repository_mock.get_recent_daily_bars.assert_not_awaited()
        self.stock_repository_mock.get_company_fundamentals_history.assert_not_awaited()
        self.thesis_repository_mock.save_rule_evaluation.assert_not_awaited()

    async def test_matched_invalidation_condition_invalidates_thesis(
        self,
    ) -> None:
        condition = self.condition.model_copy(
            update={"kind": ConditionKind.INVALIDATION}
        )
        self._configure_thesis(conditions=[condition])
        self.stock_repository_mock.get_recent_daily_bars.return_value = (
            self._daily_bars(previous_close="100", current_close="94")
        )
        self.thesis_repository_mock.list_prior_evaluations.return_value = []
        self.thesis_repository_mock.save_rule_evaluation.side_effect = (
            lambda evaluation: evaluation
        )

        async def save_event(event, evidence):
            return event, list(evidence)

        self.thesis_repository_mock.save_event_with_evidence.side_effect = save_event
        invalidated = self.thesis.model_copy(
            update={"status": ThesisStatus.INVALIDATED, "version": 2}
        )
        self.thesis_repository_mock.update_thesis.return_value = invalidated

        result = await self.service.evaluate_thesis(
            user_id=self.user_id,
            thesis_id=self.thesis.id,
            source="alpha_vantage",
        )

        self.assertEqual(result.thesis.status, ThesisStatus.INVALIDATED)
        event = result.conditions[0].event
        self.assertIsNotNone(event)
        call = self.thesis_repository_mock.update_thesis.await_args
        self.assertEqual(call.kwargs["status"], ThesisStatus.INVALIDATED)
        self.assertEqual(call.kwargs["triggering_event_id"], event.id)

    async def test_archived_thesis_is_rejected_before_loading_conditions(
        self,
    ) -> None:
        archived_thesis = self.thesis.model_copy(
            update={"status": ThesisStatus.ARCHIVED}
        )
        self.thesis_repository_mock.require_thesis.return_value = archived_thesis

        with self.assertRaises(ThesisNotMonitorableError):
            await self.service.evaluate_thesis(
                user_id=self.user_id,
                thesis_id=self.thesis.id,
                source="alpha_vantage",
            )

        self.thesis_repository_mock.list_enabled_conditions.assert_not_awaited()
        self.stock_repository_mock.get_recent_daily_bars.assert_not_awaited()
        self.stock_repository_mock.get_company_fundamentals_history.assert_not_awaited()

    def _configure_thesis(
        self,
        *,
        conditions: list[ThesisCondition],
    ) -> None:
        self.thesis_repository_mock.require_thesis.return_value = self.thesis
        self.thesis_repository_mock.list_enabled_conditions.return_value = conditions

    def _daily_bars(
        self,
        *,
        previous_close: str,
        current_close: str,
    ) -> list[DailyBar]:
        return [
            self._daily_bar(
                observation_id=uuid4(),
                trading_date=date(2026, 8, 25),
                close=previous_close,
            ),
            self._daily_bar(
                observation_id=uuid4(),
                trading_date=date(2026, 8, 26),
                close=current_close,
            ),
        ]

    @staticmethod
    def _daily_bar(
        *,
        observation_id: UUID,
        trading_date: date,
        close: str,
    ) -> DailyBar:
        close_value = Decimal(close)
        return DailyBar(
            observation_id=observation_id,
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
