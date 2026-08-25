from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class InvestmentThesisTable(Base):
    """Stores a user's investment thesis for a stock."""

    __tablename__ = "investment_theses"

    __table_args__ = (
        UniqueConstraint(
            "id",
            "user_id",
            name="investment_thesis_owner_identity",
        ),
        Index(
            "ix_investment_theses_user_symbol",
            "user_id",
            "symbol",
        ),
        CheckConstraint(
            "status IN "
            "('active', 'challenged', 'invalidated', 'archived')",
            name="status_valid",
        ),
        CheckConstraint(
            "version >= 1",
            name="version_positive",
        ),
        CheckConstraint(
            "updated_at >= created_at",
            name="timestamp_order_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )

    symbol: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ThesisConditionTable(Base):
    """Stores a deterministic condition attached to a thesis."""

    __tablename__ = "thesis_conditions"

    __table_args__ = (
        UniqueConstraint(
            "id",
            "user_id",
            name="thesis_condition_owner_identity",
        ),
        UniqueConstraint(
            "id",
            "thesis_id",
            "user_id",
            name="thesis_condition_chain_identity",
        ),
        ForeignKeyConstraint(
            ["thesis_id", "user_id"],
            [
                "investment_theses.id",
                "investment_theses.user_id",
            ],
            name="thesis_condition_thesis_owner",
            ondelete="CASCADE",
        ),
        Index(
            "ix_thesis_conditions_thesis_enabled",
            "thesis_id",
            "enabled",
        ),
        CheckConstraint(
            "kind IN ('support', 'risk', 'invalidation')",
            name="kind_valid",
        ),
        CheckConstraint(
            "operator IN "
            "('greater_than', 'greater_than_or_equal', "
            "'less_than', 'less_than_or_equal')",
            name="operator_valid",
        ),
        CheckConstraint(
            "consecutive_periods BETWEEN 1 AND 12",
            name="consecutive_periods_valid",
        ),
        CheckConstraint(
            "version >= 1",
            name="version_positive",
        ),
        CheckConstraint(
            "updated_at >= created_at",
            name="timestamp_order_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    thesis_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    metric: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    operator: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    threshold: Mapped[Decimal] = mapped_column(
        Numeric(30, 10),
        nullable=False,
    )

    consecutive_periods: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RuleEvaluationTable(Base):
    """Stores one deterministic evaluation of a thesis condition."""

    __tablename__ = "rule_evaluations"

    __table_args__ = (
        UniqueConstraint(
            "id",
            "user_id",
            name="rule_evaluation_owner_identity",
        ),
        UniqueConstraint(
            "id",
            "condition_id",
            "thesis_id",
            "user_id",
            name="rule_evaluation_chain_identity",
        ),
        UniqueConstraint(
            "condition_id",
            "rule_version",
            "data_as_of",
            name="rule_evaluation_period_identity",
        ),
        ForeignKeyConstraint(
            ["thesis_id", "user_id"],
            [
                "investment_theses.id",
                "investment_theses.user_id",
            ],
            name="rule_evaluation_thesis_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["condition_id", "thesis_id", "user_id"],
            [
                "thesis_conditions.id",
                "thesis_conditions.thesis_id",
                "thesis_conditions.user_id",
            ],
            name="rule_evaluation_condition_chain",
            ondelete="CASCADE",
        ),
        Index(
            "ix_rule_evaluations_condition_date",
            "condition_id",
            "data_as_of",
        ),
        Index(
            "ix_rule_evaluations_user_symbol",
            "user_id",
            "symbol",
        ),
        CheckConstraint(
            "operator IN "
            "('greater_than', 'greater_than_or_equal', "
            "'less_than', 'less_than_or_equal')",
            name="operator_valid",
        ),
        CheckConstraint(
            "consecutive_periods_required BETWEEN 1 AND 12",
            name="required_periods_valid",
        ),
        CheckConstraint(
            "consecutive_periods_matched BETWEEN 0 AND 12",
            name="matched_periods_valid",
        ),
        CheckConstraint(
            "consecutive_periods_matched "
            "<= consecutive_periods_required",
            name="matched_periods_not_excessive",
        ),
        CheckConstraint(
            "rule_version >= 1",
            name="rule_version_positive",
        ),
        CheckConstraint(
            "cardinality(observation_ids) > 0",
            name="observation_ids_not_empty",
        ),
        CheckConstraint(
            "matched = (consecutive_periods_matched >= consecutive_periods_required)",
            name="matched_state_consistent",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    thesis_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    condition_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )

    symbol: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
    )
    metric: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    operator: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    observed_value: Mapped[Decimal] = mapped_column(
        Numeric(30, 10),
        nullable=False,
    )
    threshold: Mapped[Decimal] = mapped_column(
        Numeric(30, 10),
        nullable=False,
    )
    matched: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    consecutive_periods_required: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    consecutive_periods_matched: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    rule_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    data_as_of: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    observation_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PostgreSQLUUID(as_uuid=True)),
        nullable=False,
        default=list,
    )


class DomainEventTable(Base):
    """Stores a structured event created by a matched evaluation."""

    __tablename__ = "domain_events"

    __table_args__ = (
        UniqueConstraint(
            "id",
            "user_id",
            name="domain_event_owner_identity",
        ),
        UniqueConstraint(
            "evaluation_id",
            name="domain_event_evaluation_identity",
        ),
        ForeignKeyConstraint(
            ["evaluation_id", "condition_id", "thesis_id", "user_id"],
            [
                "rule_evaluations.id",
                "rule_evaluations.condition_id",
                "rule_evaluations.thesis_id",
                "rule_evaluations.user_id",
            ],
            name="domain_event_evaluation_chain",
            ondelete="CASCADE",
        ),
        Index(
            "ix_domain_events_user_status",
            "user_id",
            "status",
        ),
        Index(
            "ix_domain_events_symbol_occurred",
            "symbol",
            "occurred_on",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="severity_valid",
        ),
        CheckConstraint(
            "status IN "
            "('open', 'acknowledged', 'resolved', 'dismissed')",
            name="status_valid",
        ),
        CheckConstraint(
            "rule_version >= 1",
            name="rule_version_positive",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    thesis_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    condition_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    evaluation_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )

    symbol: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="open",
        server_default="open",
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    occurred_on: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    rule_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )


class EventEvidenceTable(Base):
    """Stores auditable evidence supporting a domain event."""

    __tablename__ = "event_evidence"

    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "user_id"],
            [
                "domain_events.id",
                "domain_events.user_id",
            ],
            name="event_evidence_event_owner",
            ondelete="CASCADE",
        ),
        Index(
            "ix_event_evidence_event",
            "event_id",
        ),
        CheckConstraint(
            "evidence_type IN "
            "('metric_observation', 'market_data', "
            "'calculation', 'source_document')",
            name="evidence_type_valid",
        ),
        CheckConstraint(
            "published_at IS NULL "
            "OR published_at <= observed_at",
            name="evidence_timestamp_order_valid",
        ),
        CheckConstraint(
            "evidence_type = 'source_document' "
            "OR (metric IS NOT NULL AND observed_value IS NOT NULL)",
            name="numeric_evidence_complete",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    event_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )

    evidence_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    source_record_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )
    source_reference: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    metric: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    observed_value: Mapped[Decimal | None] = mapped_column(
        Numeric(30, 10),
        nullable=True,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    excerpt: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    data_as_of: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class EventFeedbackTable(Base):
    """Stores a user's feedback for a domain event."""

    __tablename__ = "event_feedback"

    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "user_id"],
            [
                "domain_events.id",
                "domain_events.user_id",
            ],
            name="event_feedback_event_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "event_id",
            "user_id",
            name="event_feedback_user_identity",
        ),
        Index(
            "ix_event_feedback_user_type",
            "user_id",
            "feedback_type",
        ),
        CheckConstraint(
            "feedback_type IN "
            "('useful', 'false_positive', "
            "'duplicate', 'not_relevant')",
            name="feedback_type_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    event_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )

    feedback_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )