"""
caller:
async with session.begin():
    result = await monitoring_service.evaluate_thesis(
        user_id=user_id,
        thesis_id=thesis_id,
        source="alpha_vantage",
    )
"""
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from app.data_sources.fundamental_models import CompanyFundamentals
from app.data_sources.models import DailyBar, PriceAdjustment
from app.database.repositories import StockDataRepository
from app.database.thesis_repositories import ThesisRepository
from app.domain.event_models import (
    DomainEvent,
    EventEvidence,
    EventSeverity,
    EvidenceType,
    RuleEvaluation,
)
from app.domain.metric_calculator import MetricResult
from app.domain.metric_registry import (
    MetricDefinition,
    MetricInputKind,
    get_metric_definition,
)
from app.domain.rule_engine import evaluate_condition
from app.domain.thesis_models import (
    ConditionKind,
    InvestmentThesis,
    ThesisCondition,
    ThesisStatus,
)

Clock = Callable[[], datetime]

class ThesisMonitoringError(RuntimeError):
    """Base error raised while monitoring an investment thesis."""

class ThesisNotMonitorableError(ThesisMonitoringError):
    """Raised when a thesis is not in a monitorable state."""

class InvalidMonitoringSourceError(ThesisMonitoringError):
    """Raised when a data source identifier is invalid."""

class MonitoringClockError(ThesisMonitoringError):
    """Raised when the monitoring clock returns an invalid timestamp."""


@dataclass(frozen=True, slots=True)
class ConditionMonitoringResult:
    """Result of evaluating one thesis condition."""

    condition: ThesisCondition
    metric_result: MetricResult
    evaluation: RuleEvaluation
    event: DomainEvent | None
    evidence: tuple[EventEvidence, ...]

@dataclass(frozen=True, slots=True)
class ThesisMonitoringResult:
    """Result of one deterministic thesis-monitoring run."""

    thesis: InvestmentThesis
    source: str
    started_at: datetime
    completed_at: datetime
    conditions: tuple[ConditionMonitoringResult, ...]

    @property
    def evaluation_count(self) -> int:
        return len(self.conditions)

    @property
    def matched_count(self) -> int:
        return sum(result.evaluation.matched for result in self.conditions)

    @property
    def event_count(self) -> int:
        return sum(result.event is not None for result in self.conditions)


class ThesisMonitoringService:
    """Orchestrate deterministic monitoring for ONE investment thesis.

    This service does not commit or roll back the database session.
    The caller owns the transaction so all evaluations, events, and
    evidence produced by one run can be committed atomically.
    """

    def __init__(
        self, 
        stock_data_repo: StockDataRepository,
        thesis_repo: ThesisRepository,
        *,
        clock: Clock | None = None,
        fundamental_history_limit: int = 24
    ) -> None:
        if not 2 <= fundamental_history_limit <= 1000:
            raise ValueError("fundamental_history_limit must be between 2 and 1000")

        self._stock_data_repo: StockDataRepository = stock_data_repo
        self._thesis_repo: ThesisRepository = thesis_repo
        self._clock: Clock = clock or _utc_now
        self._fundamental_history_limit: int = fundamental_history_limit

    async def evaluate_thesis(
        self,
        user_id: UUID,
        thesis_id: UUID,
        source: str,
        *,
        adjustment: PriceAdjustment = PriceAdjustment.RAW,
    ) -> ThesisMonitoringResult:
        """Evaluate ALL enabled conditions belonging to one thesis."""

        normalized_source = self._normalize_source(source)
        started_at = self._now()

        thesis = await self._thesis_repo.require_thesis(user_id=user_id, thesis_id=thesis_id)
        self._require_monitorable_thesis(thesis)

        conditions = (
            await self._thesis_repo.list_enabled_conditions(user_id=user_id, thesis_id=thesis_id)
        )

        daily_bars = await self._load_daily_bars(
            thesis=thesis,
            conditions=conditions,
            source=normalized_source,
            adjustment=adjustment
        )
        fundamentals = await self._load_fundamentals(
            thesis=thesis,
            conditions=conditions,
            source=normalized_source,
        )

        condition_results: list[ConditionMonitoringResult] = []

        # Deliberately process conditions sequentially. AsyncSession does
        # not support concurrent operations within the same transaction.
        for condition in conditions:
            result = await self._evaluate_condition(
                thesis=thesis,
                condition=condition,
                source=normalized_source,
                daily_bars=daily_bars,
                fundamentals=fundamentals,
            )
            condition_results.append(result)

        completed_at = self._now()

        return ThesisMonitoringResult(
            thesis=thesis,
            source=normalized_source,
            started_at=started_at,
            completed_at=completed_at,
            conditions=tuple(condition_results),
        )

    async def _evaluate_condition(
        self,
        thesis: InvestmentThesis,
        condition: ThesisCondition,
        source: str,
        daily_bars: Sequence[DailyBar],
        fundamentals: Sequence[CompanyFundamentals]
    ) -> ConditionMonitoringResult:

        definition = get_metric_definition(condition.metric)

        metric_result = self._calculate_metric(
            definition=definition,
            daily_bars=daily_bars,
            fundamentals=fundamentals,
        )

        prior_evaluations = await self._load_prior_evaluations(
            condition=condition,
            data_as_of=metric_result.data_as_of,
        )

        # evaluate_condition defined in rule_engine.py
        candidate_evaluation = evaluate_condition(
            thesis=thesis,
            condition=condition,
            metric_result=metric_result,
            prior_evaluations=prior_evaluations,
        )

        # The repository may return an existing evaluation when the same
        # condition version and data date have already been processed.
        evaluation = (await self._thesis_repo.save_rule_evaluation(candidate_evaluation))

        if not evaluation.matched:
            return ConditionMonitoringResult(
                condition=condition,
                metric_result=metric_result,
                evaluation=evaluation,
                event=None,
                evidence=(),
            )

        candidate_event = self._build_event(
            condition=condition,
            evaluation=evaluation,
        )

        candidate_evidence = self._build_evidence(
            event=candidate_event,
            evaluation=evaluation,
            source=source,
        )

        event, evidence = (
            await self._thesis_repo.save_event_with_evidence(
                event=candidate_event,
                evidence=candidate_evidence,
            )
        )

        return ConditionMonitoringResult(
            condition=condition,
            metric_result=metric_result,
            evaluation=evaluation,
            event=event,
            evidence=tuple(evidence)
        )

    async def _load_daily_bars(
        self,
        thesis: InvestmentThesis,
        conditions: Sequence[ThesisCondition],
        source: str,
        adjustment: PriceAdjustment,
    ) -> list[DailyBar]:
        required_observations = self._maximum_required_observations(
            conditions=conditions,
            input_kind=MetricInputKind.DAILY_BARS,
        )
        if required_observations is None:
            return []

        return (
            await self._stock_data_repo.get_recent_daily_bars(
                symbol=thesis.symbol,
                source=source,
                adjustment=adjustment,
                limit=required_observations,
            )
        )

    async def _load_fundamentals(
        self,
        thesis: InvestmentThesis,
        conditions: Sequence[ThesisCondition],
        source: str,
    ) -> list[CompanyFundamentals]:
        required_observations = self._maximum_required_observations(
            conditions=conditions,
            input_kind=MetricInputKind.FUNDAMENTALS,
        )
        if required_observations is None:
            return []

        # Fundamental fields may be missing in recent snapshots. Reading
        # additional history allows the pure calculator to find the latest
        # snapshots containing the requested field.
        limit = max(
            required_observations,
            self._fundamental_history_limit,
        )

        return await (
            self._stock_data_repo.get_company_fundamentals_history(
                symbol=thesis.symbol,
                source=source,
                limit=limit,
            )
        )

    async def _load_prior_evaluations(
        self,
        condition: ThesisCondition,
        data_as_of: date,
    ) -> list[RuleEvaluation]:
        if condition.consecutive_periods == 1:
            return []

        # RuleEvaluation stores the accumulated consecutive count, so only
        # the immediately preceding evaluation is needed.
        return await (
            self._thesis_repo.list_prior_evaluations(
                user_id=condition.user_id,
                thesis_id=condition.thesis_id,
                condition_id=condition.id,
                rule_version=condition.version,
                before=data_as_of,
                limit=1,
            )
        )

    @staticmethod
    def _calculate_metric(
        definition: MetricDefinition,
        daily_bars: Sequence[DailyBar],
        fundamentals: Sequence[CompanyFundamentals],
    ) -> MetricResult:
        if definition.input_kind is MetricInputKind.DAILY_BARS:
            return definition.calculate_daily(daily_bars)

        if definition.input_kind is MetricInputKind.FUNDAMENTALS:
            return definition.calculate_fundamentals(fundamentals)

        raise ThesisMonitoringError("Metric definition has an unsupported input kind")

    @staticmethod
    def _maximum_required_observations(conditions: Sequence[ThesisCondition], input_kind: MetricInputKind) -> int | None:
        requirements = [
            definition.required_observations
            for condition in conditions
            if (
                definition := get_metric_definition(condition.metric)
            ).input_kind is input_kind
        ]

        return max(requirements) if requirements else None

    def _build_event(
        self,
        condition: ThesisCondition,
        evaluation: RuleEvaluation,
    ) -> DomainEvent:
        return DomainEvent(
            user_id=evaluation.user_id,
            thesis_id=evaluation.thesis_id,
            condition_id=evaluation.condition_id,
            evaluation_id=evaluation.id,
            symbol=evaluation.symbol,
            event_type=(
                f"{condition.kind.value}_condition_matched"
            ),
            severity=self._severity_for(condition.kind),
            title=condition.name,
            summary=(
                f"Metric {evaluation.metric.value} produced "
                f"{evaluation.observed_value}, matching "
                f"{evaluation.operator.value} threshold "
                f"{evaluation.threshold} for "
                f"{evaluation.consecutive_periods_matched} "
                "consecutive period(s)."
            ),
            occurred_on=evaluation.data_as_of,
            detected_at=self._now(),
            rule_version=evaluation.rule_version,
        )

    @staticmethod
    def _build_evidence(
        event: DomainEvent,
        evaluation: RuleEvaluation,
        source: str,
    ) -> list[EventEvidence]:
        return [
            EventEvidence(
                event_id=event.id,
                user_id=event.user_id,
                evidence_type=EvidenceType.METRIC_OBSERVATION,
                source=source,
                source_record_id=observation_id,
                source_reference=(
                    f"{evaluation.metric.value}:{observation_id}"
                ),
                metric=evaluation.metric,
                observed_value=evaluation.observed_value,
                description=(
                    f"Normalized observation used to calculate "
                    f"{evaluation.metric.value}."
                ),
                data_as_of=evaluation.data_as_of,
                observed_at=event.detected_at,
            )
            for observation_id in evaluation.observation_ids
        ]

    @staticmethod
    def _severity_for(
        condition_kind: ConditionKind,
    ) -> EventSeverity:
        match condition_kind:
            case ConditionKind.SUPPORT:
                return EventSeverity.INFO
            case ConditionKind.RISK:
                return EventSeverity.WARNING
            case ConditionKind.INVALIDATION:
                return EventSeverity.CRITICAL

    @staticmethod
    def _require_monitorable_thesis(
        thesis: InvestmentThesis,
    ) -> None:
        monitorable_statuses = {
            ThesisStatus.ACTIVE,
            ThesisStatus.CHALLENGED,
        }

        if thesis.status not in monitorable_statuses:
            raise ThesisNotMonitorableError(f"Thesis in {thesis.status.value} status cannot be monitored")

    @staticmethod
    def _normalize_source(source: str) -> str:
        normalized = source.strip().lower()

        if not normalized:
            raise InvalidMonitoringSourceError("Data source cannot be empty")

        if len(normalized) > 50:
            raise InvalidMonitoringSourceError("Data source cannot exceed 50 characters")

        return normalized

    def _now(self) -> datetime:
        value = self._clock()

        if value.tzinfo is None or value.utcoffset() is None:
            raise MonitoringClockError("Monitoring clock must return a timezone-aware datetime")

        return value


def _utc_now() -> datetime:
    return datetime.now(UTC)