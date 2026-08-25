"""Align persisted schema with monitoring domain models.

Revision ID: 8f3c2a1d9b70
Revises: 61dab4850431
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "8f3c2a1d9b70"
down_revision: str | None = "61dab4850431"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_observation_id(table_name: str) -> None:
    op.add_column(
        table_name,
        sa.Column(
            "observation_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            f"UPDATE {table_name} "
            "SET observation_id = gen_random_uuid() "
            "WHERE observation_id IS NULL"
        )
    )
    op.alter_column(table_name, "observation_id", nullable=False)
    op.create_unique_constraint(
        op.f(f"uq_{table_name}_observation_id"),
        table_name,
        ["observation_id"],
    )


def upgrade() -> None:
    """Apply this migration."""
    _add_observation_id("daily_bars")
    _add_observation_id("fundamental_snapshots")

    op.create_table(
        "investment_theses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=15), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'challenged', 'invalidated', 'archived')",
            name=op.f("ck_investment_theses_status_valid"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_investment_theses_version_positive")),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name=op.f("ck_investment_theses_timestamp_order_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investment_theses")),
        sa.UniqueConstraint("id", "user_id", name="investment_thesis_owner_identity"),
    )
    op.create_index(
        "ix_investment_theses_user_symbol",
        "investment_theses",
        ["user_id", "symbol"],
        unique=False,
    )

    op.create_table(
        "thesis_conditions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thesis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("metric", sa.String(length=100), nullable=False),
        sa.Column("operator", sa.String(length=32), nullable=False),
        sa.Column("threshold", sa.Numeric(precision=30, scale=10), nullable=False),
        sa.Column("consecutive_periods", sa.Integer(), server_default="1", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('support', 'risk', 'invalidation')",
            name=op.f("ck_thesis_conditions_kind_valid"),
        ),
        sa.CheckConstraint(
            "operator IN ('greater_than', 'greater_than_or_equal', 'less_than', 'less_than_or_equal')",
            name=op.f("ck_thesis_conditions_operator_valid"),
        ),
        sa.CheckConstraint(
            "consecutive_periods BETWEEN 1 AND 12",
            name=op.f("ck_thesis_conditions_consecutive_periods_valid"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_thesis_conditions_version_positive")),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name=op.f("ck_thesis_conditions_timestamp_order_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["thesis_id", "user_id"],
            ["investment_theses.id", "investment_theses.user_id"],
            name="thesis_condition_thesis_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_thesis_conditions")),
        sa.UniqueConstraint("id", "user_id", name="thesis_condition_owner_identity"),
        sa.UniqueConstraint(
            "id",
            "thesis_id",
            "user_id",
            name="thesis_condition_chain_identity",
        ),
    )
    op.create_index(
        "ix_thesis_conditions_thesis_enabled",
        "thesis_conditions",
        ["thesis_id", "enabled"],
        unique=False,
    )

    op.create_table(
        "rule_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thesis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("condition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=15), nullable=False),
        sa.Column("metric", sa.String(length=100), nullable=False),
        sa.Column("operator", sa.String(length=32), nullable=False),
        sa.Column("observed_value", sa.Numeric(precision=30, scale=10), nullable=False),
        sa.Column("threshold", sa.Numeric(precision=30, scale=10), nullable=False),
        sa.Column("matched", sa.Boolean(), nullable=False),
        sa.Column("consecutive_periods_required", sa.Integer(), nullable=False),
        sa.Column("consecutive_periods_matched", sa.Integer(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("data_as_of", sa.Date(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "observation_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operator IN ('greater_than', 'greater_than_or_equal', 'less_than', 'less_than_or_equal')",
            name=op.f("ck_rule_evaluations_operator_valid"),
        ),
        sa.CheckConstraint(
            "consecutive_periods_required BETWEEN 1 AND 12",
            name=op.f("ck_rule_evaluations_required_periods_valid"),
        ),
        sa.CheckConstraint(
            "consecutive_periods_matched BETWEEN 0 AND 12",
            name=op.f("ck_rule_evaluations_matched_periods_valid"),
        ),
        sa.CheckConstraint(
            "consecutive_periods_matched <= consecutive_periods_required",
            name=op.f("ck_rule_evaluations_matched_periods_not_excessive"),
        ),
        sa.CheckConstraint(
            "rule_version >= 1",
            name=op.f("ck_rule_evaluations_rule_version_positive"),
        ),
        sa.CheckConstraint(
            "cardinality(observation_ids) > 0",
            name=op.f("ck_rule_evaluations_observation_ids_not_empty"),
        ),
        sa.CheckConstraint(
            "matched = (consecutive_periods_matched >= consecutive_periods_required)",
            name=op.f("ck_rule_evaluations_matched_state_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["thesis_id", "user_id"],
            ["investment_theses.id", "investment_theses.user_id"],
            name="rule_evaluation_thesis_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["condition_id", "thesis_id", "user_id"],
            [
                "thesis_conditions.id",
                "thesis_conditions.thesis_id",
                "thesis_conditions.user_id",
            ],
            name="rule_evaluation_condition_chain",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_evaluations")),
        sa.UniqueConstraint("id", "user_id", name="rule_evaluation_owner_identity"),
        sa.UniqueConstraint(
            "id",
            "condition_id",
            "thesis_id",
            "user_id",
            name="rule_evaluation_chain_identity",
        ),
        sa.UniqueConstraint(
            "condition_id",
            "rule_version",
            "data_as_of",
            name="rule_evaluation_period_identity",
        ),
    )
    op.create_index(
        "ix_rule_evaluations_condition_date",
        "rule_evaluations",
        ["condition_id", "data_as_of"],
        unique=False,
    )
    op.create_index(
        "ix_rule_evaluations_user_symbol",
        "rule_evaluations",
        ["user_id", "symbol"],
        unique=False,
    )

    op.create_table(
        "domain_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thesis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("condition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=15), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="open", nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name=op.f("ck_domain_events_severity_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved', 'dismissed')",
            name=op.f("ck_domain_events_status_valid"),
        ),
        sa.CheckConstraint(
            "rule_version >= 1",
            name=op.f("ck_domain_events_rule_version_positive"),
        ),
        sa.ForeignKeyConstraint(
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_domain_events")),
        sa.UniqueConstraint("id", "user_id", name="domain_event_owner_identity"),
        sa.UniqueConstraint("evaluation_id", name="domain_event_evaluation_identity"),
    )
    op.create_index(
        "ix_domain_events_user_status",
        "domain_events",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_domain_events_symbol_occurred",
        "domain_events",
        ["symbol", "occurred_on"],
        unique=False,
    )

    op.create_table(
        "event_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_reference", sa.String(length=500), nullable=True),
        sa.Column("metric", sa.String(length=100), nullable=True),
        sa.Column("observed_value", sa.Numeric(precision=30, scale=10), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("data_as_of", sa.Date(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "evidence_type IN ('metric_observation', 'market_data', 'calculation', 'source_document')",
            name=op.f("ck_event_evidence_evidence_type_valid"),
        ),
        sa.CheckConstraint(
            "published_at IS NULL OR published_at <= observed_at",
            name=op.f("ck_event_evidence_evidence_timestamp_order_valid"),
        ),
        sa.CheckConstraint(
            "evidence_type = 'source_document' OR (metric IS NOT NULL AND observed_value IS NOT NULL)",
            name=op.f("ck_event_evidence_numeric_evidence_complete"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "user_id"],
            ["domain_events.id", "domain_events.user_id"],
            name="event_evidence_event_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_evidence")),
    )
    op.create_index(
        "ix_event_evidence_event",
        "event_evidence",
        ["event_id"],
        unique=False,
    )

    op.create_table(
        "event_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feedback_type", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "feedback_type IN ('useful', 'false_positive', 'duplicate', 'not_relevant')",
            name=op.f("ck_event_feedback_feedback_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "user_id"],
            ["domain_events.id", "domain_events.user_id"],
            name="event_feedback_event_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_feedback")),
        sa.UniqueConstraint("event_id", "user_id", name="event_feedback_user_identity"),
    )
    op.create_index(
        "ix_event_feedback_user_type",
        "event_feedback",
        ["user_id", "feedback_type"],
        unique=False,
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_index("ix_event_feedback_user_type", table_name="event_feedback")
    op.drop_table("event_feedback")
    op.drop_index("ix_event_evidence_event", table_name="event_evidence")
    op.drop_table("event_evidence")
    op.drop_index("ix_domain_events_symbol_occurred", table_name="domain_events")
    op.drop_index("ix_domain_events_user_status", table_name="domain_events")
    op.drop_table("domain_events")
    op.drop_index("ix_rule_evaluations_user_symbol", table_name="rule_evaluations")
    op.drop_index("ix_rule_evaluations_condition_date", table_name="rule_evaluations")
    op.drop_table("rule_evaluations")
    op.drop_index("ix_thesis_conditions_thesis_enabled", table_name="thesis_conditions")
    op.drop_table("thesis_conditions")
    op.drop_index("ix_investment_theses_user_symbol", table_name="investment_theses")
    op.drop_table("investment_theses")

    op.drop_constraint(
        op.f("uq_fundamental_snapshots_observation_id"),
        "fundamental_snapshots",
        type_="unique",
    )
    op.drop_column("fundamental_snapshots", "observation_id")
    op.drop_constraint(
        op.f("uq_daily_bars_observation_id"),
        "daily_bars",
        type_="unique",
    )
    op.drop_column("daily_bars", "observation_id")
