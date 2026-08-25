"""
假设：
    事务由应用服务控制，Repository 只执行 flush()，不执行 commit()；
    所有读取都强制使用 user_id 做所有权过滤；
    同一条件、规则版本和数据日期只能有一条评估；
    同一评估只能生成一个事件；
    重复执行评估或事件创建时返回已存在的记录。
"""
from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.domain_tables import (
    DomainEventTable,
    EventEvidenceTable,
    EventFeedbackTable,
    InvestmentThesisTable,
    RuleEvaluationTable,
    ThesisConditionTable,
)
from app.domain.event_models import (
    DomainEvent,
    EventEvidence,
    EventFeedback,
    EventSeverity,
    EventStatus,
    EvidenceType,
    FeedbackType,
    RuleEvaluation,
)
from app.domain.thesis_models import (
    ComparisonOperator,
    ConditionKind,
    InvestmentThesis,
    MetricCode,
    ThesisCondition,
    ThesisStatus,
)

class ThesisRepositoryError(RuntimeError):
    """Base error raised by the thesis repository."""


class ResourceNotFoundError(ThesisRepositoryError):
    """Raised when a resource does not exist or is not owned by the user."""


class RepositoryConflictError(ThesisRepositoryError):
    """Raised when an entity conflicts with an existing persisted entity."""


class InvalidAggregateError(ThesisRepositoryError):
    """Raised when related domain objects do not form a valid aggregate."""


class ThesisRepository:
    """Persistence operations for investment-thesis monitoring aggregates.

    The repository never commits or rolls back the session. Transaction
    ownership belongs to the application service so evaluations, events,
    evidence, and other state changes can be committed atomically.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session: AsyncSession = session

    async def create_thesis(self, thesis: InvestmentThesis) -> InvestmentThesis:
        statement = (
            insert(InvestmentThesisTable)
            .values(
                id=thesis.id,
                user_id=thesis.user_id,
                symbol=thesis.symbol,
                title=thesis.title,
                description=thesis.description,
                status=thesis.status.value,
                version=thesis.version,
                created_at=thesis.created_at,
                updated_at=thesis.updated_at,
            )
            .on_conflict_do_nothing(index_elements=[InvestmentThesisTable.id])
            .returning(InvestmentThesisTable.id)
        )

        result = await self._session.execute(statement)
        inserted_id = result.scalar_one_or_none()

        if inserted_id is None:
            raise RepositoryConflictError("Investment thesis already exists or is inaccessible")

        # session.add() only waitlists the object for later commit, nothing happens in the database.
        # flush() will execute the SQL statement and the data will be in the database.
        # commit() finishes the transaction by committing the changes to the database, which will be visible to other transactions
        await self._session.flush()
        return thesis

    async def get_thesis(self, user_id: UUID, thesis_id: UUID) -> InvestmentThesis | None:
        statement: Select[tuple[InvestmentThesisTable]] = (
            select(InvestmentThesisTable)
            .where(
                InvestmentThesisTable.id == thesis_id,
                InvestmentThesisTable.user_id == user_id,
            )
        )

        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()

        return self._thesis_from_row(row) if row is not None else None

    async def require_thesis(self, user_id: UUID, thesis_id: UUID) -> InvestmentThesis:
        thesis = await self.get_thesis(user_id=user_id, thesis_id=thesis_id)
        if thesis is None:
            raise ResourceNotFoundError("Investment thesis not found or inaccessible")
        return thesis

    async def list_theses(
        self,
        user_id: UUID,
        *,
        symbol: str | None = None,
        status: ThesisStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[InvestmentThesis]:
        self._validate_pagination(limit=limit, offset=offset)

        statement: Select[tuple[InvestmentThesisTable]] = (
            select(InvestmentThesisTable)
            .where(InvestmentThesisTable.user_id == user_id)
        )

        if symbol is not None:
            normalized_symbol = symbol.strip().upper()
            if not normalized_symbol:
                raise ValueError("Symbol cannot be empty")
            statement = statement.where(InvestmentThesisTable.symbol == normalized_symbol)

        if status is not None:
            statement = statement.where(InvestmentThesisTable.status == status.value)

        statement = (
            statement
            .order_by(InvestmentThesisTable.updated_at.desc(), InvestmentThesisTable.id)
            .limit(limit)
            .offset(offset)
        )

        result = await self._session.execute(statement)

        return [
            self._thesis_from_row(row)
            for row in result.scalars()
        ]

    async def create_condition(self, condition: ThesisCondition) -> ThesisCondition:
        _ = await self.require_thesis(
            user_id=condition.user_id,
            thesis_id=condition.thesis_id,
        )

        statement = (
            insert(ThesisConditionTable)
            .values(
                id=condition.id,
                thesis_id=condition.thesis_id,
                user_id=condition.user_id,
                name=condition.name,
                description=condition.description,
                kind=condition.kind.value,
                metric=condition.metric.value,
                operator=condition.operator.value,
                threshold=condition.threshold,
                consecutive_periods=condition.consecutive_periods,
                enabled=condition.enabled,
                version=condition.version,
                created_at=condition.created_at,
                updated_at=condition.updated_at,
            )
            .on_conflict_do_nothing(index_elements=[ThesisConditionTable.id])
            .returning(ThesisConditionTable.id)
        )

        result = await self._session.execute(statement)
        inserted_id = result.scalar_one_or_none()

        if inserted_id is None:
            raise RepositoryConflictError("Thesis condition already exists or is inaccessible")

        await self._session.flush()
        return condition

    async def get_condition(
        self,
        user_id: UUID,
        thesis_id: UUID,
        condition_id: UUID,
    ) -> ThesisCondition | None:
        statement: Select[tuple[ThesisConditionTable]] = (
            select(ThesisConditionTable)
            .where(
                ThesisConditionTable.id == condition_id,
                ThesisConditionTable.thesis_id == thesis_id,
                ThesisConditionTable.user_id == user_id,
            )
        )

        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()

        return self._condition_from_row(row) if row is not None else None

    async def require_condition(
        self,
        user_id: UUID,
        thesis_id: UUID,
        condition_id: UUID,
    ) -> ThesisCondition:
        condition = await self.get_condition(
            user_id=user_id,
            thesis_id=thesis_id,
            condition_id=condition_id,
        )

        if condition is None:
            raise ResourceNotFoundError(
                "Thesis condition was not found"
            )

        return condition

    async def list_conditions(
        self,
        user_id: UUID,
        thesis_id: UUID,
        *,
        enabled: bool | None = None,
    ) -> list[ThesisCondition]:
        _ = await self.require_thesis(
            user_id=user_id,
            thesis_id=thesis_id,
        )

        statement: Select[tuple[ThesisConditionTable]] = (
            select(ThesisConditionTable)
            .where(
                ThesisConditionTable.thesis_id == thesis_id,
                ThesisConditionTable.user_id == user_id,
            )
        )

        if enabled is not None:
            statement = statement.where(
                ThesisConditionTable.enabled.is_(enabled)
            )

        statement = statement.order_by(
            ThesisConditionTable.created_at,
            ThesisConditionTable.id,
        )

        result = await self._session.execute(statement)

        return [
            self._condition_from_row(row)
            for row in result.scalars()
        ]

    async def list_enabled_conditions(
        self,
        user_id: UUID,
        thesis_id: UUID,
    ) -> list[ThesisCondition]:
        return await self.list_conditions(
            user_id=user_id,
            thesis_id=thesis_id,
            enabled=True,
        )

    async def save_rule_evaluation(
        self,
        evaluation: RuleEvaluation,
    ) -> RuleEvaluation:
        _ = await self.require_condition(
            user_id=evaluation.user_id,
            thesis_id=evaluation.thesis_id,
            condition_id=evaluation.condition_id,
        )

        statement = (
            insert(RuleEvaluationTable)
            .values(
                id=evaluation.id,
                user_id=evaluation.user_id,
                thesis_id=evaluation.thesis_id,
                condition_id=evaluation.condition_id,
                symbol=evaluation.symbol,
                metric=evaluation.metric.value,
                operator=evaluation.operator.value,
                observed_value=evaluation.observed_value,
                threshold=evaluation.threshold,
                matched=evaluation.matched,
                consecutive_periods_required=(
                    evaluation.consecutive_periods_required
                ),
                consecutive_periods_matched=(
                    evaluation.consecutive_periods_matched
                ),
                rule_version=evaluation.rule_version,
                data_as_of=evaluation.data_as_of,
                evaluated_at=evaluation.evaluated_at,
                observation_ids=list(evaluation.observation_ids),
            )
            .on_conflict_do_nothing(constraint="rule_evaluation_period_identity")
            .returning(RuleEvaluationTable.id)
        )

        result = await self._session.execute(statement)
        inserted_id = result.scalar_one_or_none()

        if inserted_id is not None:
            await self._session.flush()
            return evaluation

        existing = await self.get_rule_evaluation_for_period(
            user_id=evaluation.user_id,
            thesis_id=evaluation.thesis_id,
            condition_id=evaluation.condition_id,
            rule_version=evaluation.rule_version,
            data_as_of=evaluation.data_as_of,
        )

        if existing is None:
            raise RepositoryConflictError("Rule evaluation could not be persisted")

        return existing

    async def get_rule_evaluation(
        self,
        user_id: UUID,
        evaluation_id: UUID,
    ) -> RuleEvaluation | None:
        statement: Select[tuple[RuleEvaluationTable]] = (
            select(RuleEvaluationTable)
            .where(
                RuleEvaluationTable.id == evaluation_id,
                RuleEvaluationTable.user_id == user_id,
            )
        )

        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()

        return self._evaluation_from_row(row) if row is not None else None

    async def get_rule_evaluation_for_period(
        self,
        user_id: UUID,
        thesis_id: UUID,
        condition_id: UUID,
        rule_version: int,
        data_as_of: date,
    ) -> RuleEvaluation | None:
        statement: Select[tuple[RuleEvaluationTable]] = (
            select(RuleEvaluationTable)
            .where(
                RuleEvaluationTable.user_id == user_id,
                RuleEvaluationTable.thesis_id == thesis_id,
                RuleEvaluationTable.condition_id == condition_id,
                RuleEvaluationTable.rule_version == rule_version,
                RuleEvaluationTable.data_as_of == data_as_of,
            )
        )

        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()

        return self._evaluation_from_row(row) if row is not None else None

    async def list_prior_evaluations(
        self,
        user_id: UUID,
        thesis_id: UUID,
        condition_id: UUID,
        rule_version: int,
        before: date,
        *,
        limit: int = 12,
    ) -> list[RuleEvaluation]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")

        _ = await self.require_condition(
            user_id=user_id,
            thesis_id=thesis_id,
            condition_id=condition_id,
        )

        statement: Select[tuple[RuleEvaluationTable]] = (
            select(RuleEvaluationTable)
            .where(
                RuleEvaluationTable.user_id == user_id,
                RuleEvaluationTable.thesis_id == thesis_id,
                RuleEvaluationTable.condition_id == condition_id,
                RuleEvaluationTable.rule_version == rule_version,
                RuleEvaluationTable.data_as_of < before,
            )
            .order_by(
                RuleEvaluationTable.data_as_of.desc(),
                RuleEvaluationTable.evaluated_at.desc(),
            )
            .limit(limit)
        )

        result = await self._session.execute(statement)
        rows = list(result.scalars())
        rows.reverse()

        return [
            self._evaluation_from_row(row)
            for row in rows
        ]

    async def save_event_with_evidence(
        self,
        event: DomainEvent,
        evidence: Sequence[EventEvidence],
    ) -> tuple[DomainEvent, list[EventEvidence]]:
        evaluation = await self.get_rule_evaluation(
            user_id=event.user_id,
            evaluation_id=event.evaluation_id,
        )

        if evaluation is None:
            raise ResourceNotFoundError(
                "Rule evaluation was not found"
            )

        self._validate_event_relationship(
            event=event,
            evaluation=evaluation,
        )
        self._validate_evidence_relationships(
            event=event,
            evidence=evidence,
        )

        statement = (
            insert(DomainEventTable)
            .values(
                id=event.id,
                user_id=event.user_id,
                thesis_id=event.thesis_id,
                condition_id=event.condition_id,
                evaluation_id=event.evaluation_id,
                symbol=event.symbol,
                event_type=event.event_type,
                severity=event.severity.value,
                status=event.status.value,
                title=event.title,
                summary=event.summary,
                occurred_on=event.occurred_on,
                detected_at=event.detected_at,
                rule_version=event.rule_version,
            )
            .on_conflict_do_nothing(
                constraint="domain_event_evaluation_identity",
            )
            .returning(DomainEventTable.id)
        )

        result = await self._session.execute(statement)
        inserted_id = result.scalar_one_or_none()

        if inserted_id is None:
            existing_event = await self.get_event_by_evaluation(
                user_id=event.user_id,
                evaluation_id=event.evaluation_id,
            )

            if existing_event is None:
                raise RepositoryConflictError("Domain event could not be persisted")

            existing_evidence = await self.list_event_evidence(
                user_id=event.user_id,
                event_id=existing_event.id,
            )
            return existing_event, existing_evidence

        if evidence:
            _ = await self._session.execute(
                insert(EventEvidenceTable),
                [
                    {
                        "id": item.id,
                        "event_id": event.id,
                        "user_id": event.user_id,
                        "evidence_type": item.evidence_type.value,
                        "source": item.source.strip().lower(),
                        "source_record_id": item.source_record_id,
                        "source_reference": item.source_reference,
                        "metric": (
                            item.metric.value
                            if item.metric is not None
                            else None
                        ),
                        "observed_value": item.observed_value,
                        "description": item.description,
                        "excerpt": item.excerpt,
                        "data_as_of": item.data_as_of,
                        "published_at": item.published_at,
                        "observed_at": item.observed_at,
                    }
                    for item in evidence
                ],
            )

        await self._session.flush()
        return event, list(evidence)

    async def get_event(
        self,
        user_id: UUID,
        event_id: UUID,
    ) -> DomainEvent | None:
        statement: Select[tuple[DomainEventTable]] = (
            select(DomainEventTable)
            .where(
                DomainEventTable.id == event_id,
                DomainEventTable.user_id == user_id,
            )
        )

        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()

        return self._event_from_row(row) if row is not None else None

    async def get_event_by_evaluation(
        self,
        user_id: UUID,
        evaluation_id: UUID,
    ) -> DomainEvent | None:
        statement: Select[tuple[DomainEventTable]] = (
            select(DomainEventTable)
            .where(
                DomainEventTable.evaluation_id == evaluation_id,
                DomainEventTable.user_id == user_id,
            )
        )

        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()

        return self._event_from_row(row) if row is not None else None

    async def list_events(
        self,
        user_id: UUID,
        *,
        thesis_id: UUID | None = None,
        status: EventStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DomainEvent]:
        self._validate_pagination(limit=limit, offset=offset)

        statement: Select[tuple[DomainEventTable]] = (
            select(DomainEventTable)
            .where(DomainEventTable.user_id == user_id)
        )

        if thesis_id is not None:
            statement = statement.where(
                DomainEventTable.thesis_id == thesis_id
            )

        if status is not None:
            statement = statement.where(
                DomainEventTable.status == status.value
            )

        statement = (
            statement
            .order_by(
                DomainEventTable.occurred_on.desc(),
                DomainEventTable.detected_at.desc(),
                DomainEventTable.id,
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self._session.execute(statement)

        return [
            self._event_from_row(row)
            for row in result.scalars()
        ]

    async def list_event_evidence(
        self,
        user_id: UUID,
        event_id: UUID,
    ) -> list[EventEvidence]:
        event = await self.get_event(
            user_id=user_id,
            event_id=event_id,
        )
        if event is None:
            raise ResourceNotFoundError(
                "Domain event was not found"
            )

        statement: Select[tuple[EventEvidenceTable]] = (
            select(EventEvidenceTable)
            .where(
                EventEvidenceTable.event_id == event_id,
                EventEvidenceTable.user_id == user_id,
            )
            .order_by(
                EventEvidenceTable.observed_at,
                EventEvidenceTable.id,
            )
        )

        result = await self._session.execute(statement)

        return [
            self._evidence_from_row(row)
            for row in result.scalars()
        ]

    async def save_feedback(
        self,
        feedback: EventFeedback,
    ) -> EventFeedback:
        event = await self.get_event(
            user_id=feedback.user_id,
            event_id=feedback.event_id,
        )
        if event is None:
            raise ResourceNotFoundError(
                "Domain event was not found"
            )

        statement = (
            insert(EventFeedbackTable)
            .values(
                id=feedback.id,
                event_id=feedback.event_id,
                user_id=feedback.user_id,
                feedback_type=feedback.feedback_type.value,
                comment=feedback.comment,
                created_at=feedback.created_at,
            )
            .on_conflict_do_update(
                constraint="event_feedback_user_identity",
                set_={
                    "feedback_type": feedback.feedback_type.value,
                    "comment": feedback.comment,
                },
            )
            .returning(EventFeedbackTable.id)
        )

        _ = await self._session.execute(statement)
        await self._session.flush()

        persisted = await self.get_feedback(
            user_id=feedback.user_id,
            event_id=feedback.event_id,
        )

        if persisted is None:
            raise RepositoryConflictError(
                "Event feedback could not be persisted"
            )

        return persisted

    async def get_feedback(
        self,
        user_id: UUID,
        event_id: UUID,
    ) -> EventFeedback | None:
        statement: Select[tuple[EventFeedbackTable]] = (
            select(EventFeedbackTable)
            .where(
                EventFeedbackTable.event_id == event_id,
                EventFeedbackTable.user_id == user_id,
            )
        )

        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()

        return self._feedback_from_row(row) if row is not None else None

    @staticmethod
    def _validate_event_relationship(
        event: DomainEvent,
        evaluation: RuleEvaluation,
    ) -> None:
        if not evaluation.matched:
            raise InvalidAggregateError(
                "An event can only be created from a matched evaluation"
            )

        if event.user_id != evaluation.user_id:
            raise InvalidAggregateError(
                "Event and evaluation users do not match"
            )
        if event.thesis_id != evaluation.thesis_id:
            raise InvalidAggregateError(
                "Event and evaluation theses do not match"
            )
        if event.condition_id != evaluation.condition_id:
            raise InvalidAggregateError(
                "Event and evaluation conditions do not match"
            )
        if event.symbol != evaluation.symbol:
            raise InvalidAggregateError(
                "Event and evaluation symbols do not match"
            )
        if event.rule_version != evaluation.rule_version:
            raise InvalidAggregateError(
                "Event and evaluation rule versions do not match"
            )
        if event.occurred_on != evaluation.data_as_of:
            raise InvalidAggregateError(
                "Event date must match the evaluation data date"
            )

    @staticmethod
    def _validate_evidence_relationships(
        event: DomainEvent,
        evidence: Sequence[EventEvidence],
    ) -> None:
        evidence_ids: set[UUID] = set()

        for item in evidence:
            if item.id in evidence_ids:
                raise InvalidAggregateError(
                    "Evidence IDs must be unique"
                )
            evidence_ids.add(item.id)

            if item.event_id != event.id:
                raise InvalidAggregateError(
                    "Evidence is not associated with the event"
                )
            if item.user_id != event.user_id:
                raise InvalidAggregateError(
                    "Evidence is not associated with the event owner"
                )

    @staticmethod
    def _validate_pagination(
        limit: int,
        offset: int,
    ) -> None:
        if not 1 <= limit <= 500:
            raise ValueError("Limit must be between 1 and 500")
        if offset < 0:
            raise ValueError("Offset cannot be negative")

    @staticmethod
    def _thesis_from_row(
        row: InvestmentThesisTable,
    ) -> InvestmentThesis:
        return InvestmentThesis(
            id=row.id,
            user_id=row.user_id,
            symbol=row.symbol,
            title=row.title,
            description=row.description,
            status=ThesisStatus(row.status),
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _condition_from_row(
        row: ThesisConditionTable,
    ) -> ThesisCondition:
        return ThesisCondition(
            id=row.id,
            thesis_id=row.thesis_id,
            user_id=row.user_id,
            name=row.name,
            description=row.description,
            kind=ConditionKind(row.kind),
            metric=MetricCode(row.metric),
            operator=ComparisonOperator(row.operator),
            threshold=row.threshold,
            consecutive_periods=row.consecutive_periods,
            enabled=row.enabled,
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _evaluation_from_row(
        row: RuleEvaluationTable,
    ) -> RuleEvaluation:
        return RuleEvaluation(
            id=row.id,
            user_id=row.user_id,
            thesis_id=row.thesis_id,
            condition_id=row.condition_id,
            symbol=row.symbol,
            metric=MetricCode(row.metric),
            operator=ComparisonOperator(row.operator),
            observed_value=row.observed_value,
            threshold=row.threshold,
            matched=row.matched,
            consecutive_periods_required=(
                row.consecutive_periods_required
            ),
            consecutive_periods_matched=(
                row.consecutive_periods_matched
            ),
            rule_version=row.rule_version,
            data_as_of=row.data_as_of,
            evaluated_at=row.evaluated_at,
            observation_ids=tuple(row.observation_ids),
        )

    @staticmethod
    def _event_from_row(
        row: DomainEventTable,
    ) -> DomainEvent:
        return DomainEvent(
            id=row.id,
            user_id=row.user_id,
            thesis_id=row.thesis_id,
            condition_id=row.condition_id,
            evaluation_id=row.evaluation_id,
            symbol=row.symbol,
            event_type=row.event_type,
            severity=EventSeverity(row.severity),
            status=EventStatus(row.status),
            title=row.title,
            summary=row.summary,
            occurred_on=row.occurred_on,
            detected_at=row.detected_at,
            rule_version=row.rule_version,
        )

    @staticmethod
    def _evidence_from_row(
        row: EventEvidenceTable,
    ) -> EventEvidence:
        return EventEvidence(
            id=row.id,
            event_id=row.event_id,
            user_id=row.user_id,
            evidence_type=EvidenceType(row.evidence_type),
            source=row.source,
            source_record_id=row.source_record_id,
            source_reference=row.source_reference,
            metric=MetricCode(row.metric) if row.metric is not None else None,
            observed_value=row.observed_value,
            description=row.description,
            excerpt=row.excerpt,
            data_as_of=row.data_as_of,
            published_at=row.published_at,
            observed_at=row.observed_at,
        )

    @staticmethod
    def _feedback_from_row(
        row: EventFeedbackTable,
    ) -> EventFeedback:
        return EventFeedback(
            id=row.id,
            event_id=row.event_id,
            user_id=row.user_id,
            feedback_type=FeedbackType(row.feedback_type),
            comment=row.comment,
            created_at=row.created_at,
        )