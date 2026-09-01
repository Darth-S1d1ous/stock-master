"""Complete the operational backend data model.

Revision ID: c4d8e2f1a930
Revises: 8f3c2a1d9b70
Create Date: 2026-08-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c4d8e2f1a930"
down_revision: str | None = "8f3c2a1d9b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ingestion auditing, lifecycle history, and feedback history."""

    op.drop_constraint(
        "event_feedback_user_identity",
        "event_feedback",
        type_="unique",
    )
    op.drop_constraint(
        op.f("ck_event_feedback_feedback_type_valid"),
        "event_feedback",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_event_feedback_feedback_type_valid"),
        "event_feedback",
        "feedback_type IN ('useful', 'not_useful', 'false_positive', "
        "'confirmed', 'ignored', 'duplicate', 'not_relevant')",
    )
    op.create_index(
        "ix_event_feedback_event_created",
        "event_feedback",
        ["event_id", "user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "thesis_condition_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("condition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thesis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("metric", sa.String(length=100), nullable=False),
        sa.Column("operator", sa.String(length=32), nullable=False),
        sa.Column("threshold", sa.Numeric(precision=30, scale=10), nullable=False),
        sa.Column("consecutive_periods", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version >= 1",
            name=op.f("ck_thesis_condition_versions_version_positive"),
        ),
        sa.CheckConstraint(
            "kind IN ('support', 'risk', 'invalidation')",
            name=op.f("ck_thesis_condition_versions_kind_valid"),
        ),
        sa.CheckConstraint(
            "operator IN ('greater_than', 'greater_than_or_equal', 'less_than', 'less_than_or_equal')",
            name=op.f("ck_thesis_condition_versions_operator_valid"),
        ),
        sa.CheckConstraint(
            "consecutive_periods BETWEEN 1 AND 12",
            name=op.f("ck_thesis_condition_versions_consecutive_periods_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["condition_id", "thesis_id", "user_id"],
            [
                "thesis_conditions.id",
                "thesis_conditions.thesis_id",
                "thesis_conditions.user_id",
            ],
            name="thesis_condition_version_condition_chain",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_thesis_condition_versions")),
        sa.UniqueConstraint(
            "condition_id", "version", name="thesis_condition_version_identity"
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO thesis_condition_versions "
            "(id, condition_id, thesis_id, user_id, version, name, description, kind, "
            "metric, operator, threshold, consecutive_periods, enabled, created_at) "
            "SELECT gen_random_uuid(), id, thesis_id, user_id, version, name, description, "
            "kind, metric, operator, threshold, consecutive_periods, enabled, created_at "
            "FROM thesis_conditions"
        )
    )
    op.create_index(
        "ix_thesis_condition_versions_condition_created",
        "thesis_condition_versions",
        ["condition_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("succeeded_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("mode IN ('symbol', 'active')", name=op.f("ck_ingestion_runs_mode_valid")),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'partial', 'failed')",
            name=op.f("ck_ingestion_runs_status_valid"),
        ),
        sa.CheckConstraint(
            "requested_count >= 0 AND succeeded_count >= 0 AND failed_count >= 0",
            name=op.f("ck_ingestion_runs_counts_non_negative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_runs")),
    )
    op.create_index(
        "ix_ingestion_runs_source_started",
        "ingestion_runs",
        ["source", "started_at"],
        unique=False,
    )

    op.create_table(
        "ingestion_run_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=15), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("daily_bars_processed", sa.Integer(), nullable=False),
        sa.Column("fundamental_snapshot_date", sa.Date(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name=op.f("ck_ingestion_run_items_status_valid"),
        ),
        sa.CheckConstraint(
            "daily_bars_processed >= 0",
            name=op.f("ck_ingestion_run_items_daily_bars_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ingestion_runs.id"],
            name="ingestion_run_item_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_run_items")),
        sa.UniqueConstraint("run_id", "symbol", name="ingestion_run_item_identity"),
    )
    op.create_index(
        "ix_ingestion_run_items_run_status",
        "ingestion_run_items",
        ["run_id", "status"],
        unique=False,
    )

    op.create_table(
        "thesis_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thesis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=False),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("triggering_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "from_status IN ('active', 'challenged', 'invalidated', 'archived')",
            name=op.f("ck_thesis_status_history_from_status_valid"),
        ),
        sa.CheckConstraint(
            "to_status IN ('active', 'challenged', 'invalidated', 'archived')",
            name=op.f("ck_thesis_status_history_to_status_valid"),
        ),
        sa.CheckConstraint(
            "from_status <> to_status",
            name=op.f("ck_thesis_status_history_status_changed"),
        ),
        sa.ForeignKeyConstraint(
            ["thesis_id", "user_id"],
            ["investment_theses.id", "investment_theses.user_id"],
            name="thesis_status_history_thesis_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["triggering_event_id", "user_id"],
            ["domain_events.id", "domain_events.user_id"],
            name="thesis_status_history_triggering_event_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_thesis_status_history")),
    )
    op.create_index(
        "ix_thesis_status_history_thesis_changed",
        "thesis_status_history",
        ["thesis_id", "changed_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove operational backend data model additions."""

    op.drop_index(
        "ix_thesis_status_history_thesis_changed",
        table_name="thesis_status_history",
    )
    op.drop_table("thesis_status_history")
    op.drop_index(
        "ix_ingestion_run_items_run_status",
        table_name="ingestion_run_items",
    )
    op.drop_table("ingestion_run_items")
    op.drop_index("ix_ingestion_runs_source_started", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_index(
        "ix_thesis_condition_versions_condition_created",
        table_name="thesis_condition_versions",
    )
    op.drop_table("thesis_condition_versions")

    op.drop_index("ix_event_feedback_event_created", table_name="event_feedback")
    op.drop_constraint(
        op.f("ck_event_feedback_feedback_type_valid"),
        "event_feedback",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_event_feedback_feedback_type_valid"),
        "event_feedback",
        "feedback_type IN ('useful', 'false_positive', 'duplicate', 'not_relevant')",
    )
    op.create_unique_constraint(
        "event_feedback_user_identity",
        "event_feedback",
        ["event_id", "user_id"],
    )
