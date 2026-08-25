from datetime import UTC, date, datetime
from decimal import Decimal
import unittest
from uuid import uuid4

import httpx
from pydantic import ValidationError

from app.data_sources.alpha_vantage_client import (
    AlphaVantageClient,
    AlphaVantageRequestError,
)
from app.data_sources.fundamental_models import CompanyFundamentals
from app.data_sources.models import DailyBar
from app.data_sources.settings import DataSourceSettings
from app.database.base import Base
from app.database.domain_tables import (
    DomainEventTable,
    EventEvidenceTable,
    InvestmentThesisTable,
    RuleEvaluationTable,
    ThesisConditionTable,
)
from app.database.tables import DailyBarTable, FundamentalSnapshotTable
from app.domain.event_models import EventSeverity
from app.domain.metric_calculator import MetricResult, calculate_pe_ratio
from app.domain.rule_engine import evaluate_condition
from app.domain.thesis_models import (
    ComparisonOperator,
    ConditionKind,
    InvestmentThesis,
    MetricCode,
    ThesisCondition,
)


class RedirectSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_injected_client_cannot_enable_redirects(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                status_code=302,
                headers={"Location": "http://127.0.0.1/private"},
                request=request,
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            follow_redirects=True,
        ) as http_client:
            client = AlphaVantageClient(
                settings=DataSourceSettings(alpha_vantage_api_key="secret"),
                http_client=http_client,
            )
            with self.assertRaises(AlphaVantageRequestError):
                await client.fetch_daily_raw("AAPL")

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url.host, "www.alphavantage.co")


class ContractRegressionTests(unittest.TestCase):
    def test_provider_keys_are_redacted(self) -> None:
        settings = DataSourceSettings(
            alpha_vantage_api_key="alpha-secret",
            finnhub_api_key="finnhub-secret",
        )

        representation = repr(settings)

        self.assertNotIn("alpha-secret", representation)
        self.assertNotIn("finnhub-secret", representation)

    def test_provider_urls_reject_unapproved_hosts(self) -> None:
        invalid_urls = (
            {"alpha_vantage_base_url": "http://www.alphavantage.co/query"},
            {"alpha_vantage_base_url": "https://127.0.0.1/query"},
            {"finnhub_base_url": "https://10.0.0.1"},
            {"finnhub_base_url": "https://user:pass@finnhub.io"},
        )

        for values in invalid_urls:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                DataSourceSettings(**values)

    def test_rule_evaluation_matches_database_enum_values(self) -> None:
        self.assertEqual(EventSeverity.INFO.value, "info")
        self.assertEqual(EventSeverity.WARNING.value, "warning")
        self.assertEqual(EventSeverity.CRITICAL.value, "critical")

    def test_rule_evaluation_requires_auditable_observations(self) -> None:
        now = datetime.now(UTC)
        user_id = uuid4()
        thesis_id = uuid4()
        condition_id = uuid4()
        thesis = InvestmentThesis(
            id=thesis_id,
            user_id=user_id,
            symbol="AAPL",
            title="Price risk",
            description="Monitor daily downside.",
            created_at=now,
            updated_at=now,
        )
        condition = ThesisCondition(
            id=condition_id,
            thesis_id=thesis_id,
            user_id=user_id,
            name="Daily decline",
            kind=ConditionKind.RISK,
            metric=MetricCode.DAILY_PRICE_CHANGE_PERCENT,
            operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            threshold=Decimal("-5"),
            created_at=now,
            updated_at=now,
        )
        metric_result = MetricResult(
            metric=MetricCode.DAILY_PRICE_CHANGE_PERCENT,
            value=Decimal("-6"),
            data_as_of=date(2026, 8, 25),
            observation_ids=(uuid4(), uuid4()),
        )

        evaluation = evaluate_condition(thesis, condition, metric_result)

        self.assertTrue(evaluation.matched)
        self.assertEqual(evaluation.observation_ids, metric_result.observation_ids)

    def test_orm_metadata_contains_monitoring_contracts(self) -> None:
        expected_tables = {
            "daily_bars",
            "fundamental_snapshots",
            "investment_theses",
            "thesis_conditions",
            "rule_evaluations",
            "domain_events",
            "event_evidence",
            "event_feedback",
        }
        self.assertTrue(expected_tables.issubset(Base.metadata.tables))
        self.assertFalse(DailyBarTable.__table__.c.observation_id.nullable)
        self.assertFalse(FundamentalSnapshotTable.__table__.c.observation_id.nullable)

        condition_constraints = {
            constraint.name for constraint in ThesisConditionTable.__table__.constraints
        }
        evaluation_constraints = {
            constraint.name for constraint in RuleEvaluationTable.__table__.constraints
        }
        event_constraints = {
            constraint.name for constraint in DomainEventTable.__table__.constraints
        }
        thesis_constraints = {
            constraint.name for constraint in InvestmentThesisTable.__table__.constraints
        }

        self.assertIn("investment_thesis_owner_identity", thesis_constraints)
        self.assertIn("thesis_condition_chain_identity", condition_constraints)
        self.assertIn("rule_evaluation_period_identity", evaluation_constraints)
        self.assertIn("rule_evaluation_chain_identity", evaluation_constraints)
        self.assertIn("domain_event_evaluation_chain", event_constraints)
        evidence_constraints = {
            constraint.name for constraint in EventEvidenceTable.__table__.constraints
        }
        self.assertIn(
            "ck_event_evidence_numeric_evidence_complete",
            evidence_constraints,
        )

    def test_source_names_and_provider_urls_are_normalized(self) -> None:
        received_at = datetime.now(UTC)
        bar = DailyBar(
            symbol="AAPL",
            trading_date=date(2026, 8, 25),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=100,
            source=" Finnhub ",
            received_at=received_at,
        )
        fundamentals = CompanyFundamentals(
            symbol="AAPL",
            pe_ratio=Decimal("20"),
            source=" Alpha_Vantage ",
            received_at=received_at,
        )
        settings = DataSourceSettings(
            finnhub_base_url=" https://finnhub.io/ ",
        )

        self.assertEqual(bar.source, "finnhub")
        self.assertEqual(fundamentals.source, "alpha_vantage")
        self.assertEqual(settings.finnhub_base_url, "https://finnhub.io")

    def test_fundamental_metric_uses_snapshot_date(self) -> None:
        observation_id = uuid4()
        snapshot = CompanyFundamentals(
            observation_id=observation_id,
            snapshot_date=date(2026, 6, 30),
            symbol="AAPL",
            pe_ratio=Decimal("20"),
            source="alpha_vantage",
            received_at=datetime(2026, 8, 25, tzinfo=UTC),
        )

        result = calculate_pe_ratio([snapshot])

        self.assertEqual(result.data_as_of, date(2026, 6, 30))
        self.assertEqual(result.observation_ids, (observation_id,))


if __name__ == "__main__":
    unittest.main()
