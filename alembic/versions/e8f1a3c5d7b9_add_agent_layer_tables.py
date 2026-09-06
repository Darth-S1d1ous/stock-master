"""Add agent session, memory, and condition-write tables.

Revision ID: e8f1a3c5d7b9
Revises: c4d8e2f1a930
Create Date: 2026-09-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e8f1a3c5d7b9"
down_revision: str | None = "c4d8e2f1a930"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist condition-authoring sessions and their audit trail."""

    op.create_table(
        "agent_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thesis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=15), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="open",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('open', 'closed')",
            name=op.f("ck_agent_sessions_status_valid"),
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name=op.f("ck_agent_sessions_timestamp_order_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["thesis_id", "user_id"],
            ["investment_theses.id", "investment_theses.user_id"],
            name="agent_session_thesis_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_sessions")),
        sa.UniqueConstraint(
            "id",
            "user_id",
            name="agent_session_owner_identity",
        ),
        sa.UniqueConstraint(
            "id",
            "thesis_id",
            "user_id",
            name="agent_session_thesis_chain",
        ),
    )
    op.create_index(
        "ix_agent_sessions_user_symbol",
        "agent_sessions",
        ["user_id", "symbol"],
        unique=False,
    )
    op.create_index(
        "uq_agent_sessions_one_open_per_thesis",
        "agent_sessions",
        ["user_id", "thesis_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "agent_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.String(length=20000), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=True),
        sa.Column("tool_call_id", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('system', 'user', 'assistant', 'tool')",
            name=op.f("ck_agent_messages_role_valid"),
        ),
        sa.CheckConstraint(
            "("
            "role = 'tool' AND tool_name IS NOT NULL AND tool_call_id IS NOT NULL"
            ") OR ("
            "role <> 'tool' AND tool_name IS NULL AND tool_call_id IS NULL"
            ")",
            name=op.f("ck_agent_messages_tool_fields_match_role"),
        ),
        sa.CheckConstraint(
            "("
            "role = 'assistant'"
            ") OR ("
            "model IS NULL AND prompt_version IS NULL"
            ")",
            name=op.f("ck_agent_messages_model_fields_match_role"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["agent_sessions.id", "agent_sessions.user_id"],
            name="agent_message_session_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_messages")),
        sa.UniqueConstraint(
            "id",
            "user_id",
            name="agent_message_owner_identity",
        ),
        sa.UniqueConstraint(
            "id",
            "session_id",
            "user_id",
            name="agent_message_session_chain",
        ),
    )
    op.create_index(
        "ix_agent_messages_session_created",
        "agent_messages",
        ["session_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "agent_memory",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary", sa.String(length=8000), nullable=False),
        sa.Column("message_count_at_summary", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "message_count_at_summary >= 1",
            name=op.f("ck_agent_memory_message_count_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["agent_sessions.id", "agent_sessions.user_id"],
            name="agent_memory_session_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_memory")),
        sa.UniqueConstraint(
            "session_id",
            name="agent_memory_session_identity",
        ),
    )

    op.create_table(
        "agent_condition_writes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thesis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("condition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('create', 'update')",
            name=op.f("ck_agent_condition_writes_action_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "thesis_id", "user_id"],
            [
                "agent_sessions.id",
                "agent_sessions.thesis_id",
                "agent_sessions.user_id",
            ],
            name="agent_condition_write_session_chain",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id", "session_id", "user_id"],
            [
                "agent_messages.id",
                "agent_messages.session_id",
                "agent_messages.user_id",
            ],
            name="agent_condition_write_message_chain",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["condition_id", "thesis_id", "user_id"],
            [
                "thesis_conditions.id",
                "thesis_conditions.thesis_id",
                "thesis_conditions.user_id",
            ],
            name="agent_condition_write_condition_chain",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_condition_writes")),
    )
    op.create_index(
        "ix_agent_condition_writes_condition",
        "agent_condition_writes",
        ["condition_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove agent-layer tables."""

    op.drop_index(
        "ix_agent_condition_writes_condition",
        table_name="agent_condition_writes",
    )
    op.drop_table("agent_condition_writes")
    op.drop_table("agent_memory")
    op.drop_index(
        "ix_agent_messages_session_created",
        table_name="agent_messages",
    )
    op.drop_table("agent_messages")
    op.drop_index(
        "uq_agent_sessions_one_open_per_thesis",
        table_name="agent_sessions",
    )
    op.drop_index(
        "ix_agent_sessions_user_symbol",
        table_name="agent_sessions",
    )
    op.drop_table("agent_sessions")