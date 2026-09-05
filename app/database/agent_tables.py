from datetime import datetime
from uuid import UUID 

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

class AgentSessionTable(Base):
    """Stores one condition-authoring session for a saved thesis."""

    __tablename__ = "agent_sessions"

    __table_args__ = (
        UniqueConstraint(
            "id",
            "user_id",
            name="agent_session_owner_identity",
        ),
        UniqueConstraint(
            "id",
            "thesis_id",
            "user_id",
            name="agent_session_thesis_chain",
        ),
        ForeignKeyConstraint(
            ["thesis_id", "user_id"],
            ["investment_theses.id", "investment_theses.user_id"],
            name="agent_session_thesis_owner",
            ondelete="CASCADE",
        ),
        Index(
            "ix_agent_sessions_user_symbol",
            "user_id",
            "symbol",
        ),
        Index(
            "uq_agent_sessions_one_open_per_thesis",
            "user_id",
            "thesis_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        CheckConstraint(
            "status IN ('open', 'closed')",
            name="status_valid",
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
    thesis_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="open",
        server_default="open",
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

class AgentMessageTable(Base):
    """Stores append-only turns that make up session working memory."""

    __tablename__ = "agent_messages"

    __table_args__ = (
        UniqueConstraint(
            "id",
            "user_id",
            name="agent_message_owner_identity",
        ),
        UniqueConstraint(
            "id",
            "session_id",
            "user_id",
            name="agent_message_session_chain",
        ),
        ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["agent_sessions.id", "agent_sessions.user_id"],
            name="agent_message_session_owner",
            ondelete="CASCADE",
        ),
        Index(
            "ix_agent_messages_session_created",
            "session_id",
            "created_at",
        ),
        CheckConstraint(
            "role IN ('system', 'user', 'assistant', 'tool')",
            name="role_valid",
        ),
        CheckConstraint(
            "("
            "role = 'tool' AND tool_name IS NOT NULL AND tool_call_id IS NOT NULL"
            ") OR ("
            "role <> 'tool' AND tool_name IS NULL AND tool_call_id IS NULL"
            ")",
            name="tool_fields_match_role",
        ),
        CheckConstraint(
            "("
            "role = 'assistant'"
            ") OR ("
            "model IS NULL AND prompt_version IS NULL"
            ")",
            name="model_fields_match_role",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        String(20000),
        nullable=False,
    )
    tool_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    tool_call_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    prompt_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

class AgentMemoryTable(Base):
    """Stores one rolling summary per session."""

    __tablename__ = "agent_memory"

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            name="agent_memory_session_identity",
        ),
        ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["agent_sessions.id", "agent_sessions.user_id"],
            name="agent_memory_session_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "message_count_at_summary >= 1",
            name="message_count_positive",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(
        String(8000),
        nullable=False,
    )
    message_count_at_summary: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

class AgentConditionWriteTable(Base):
    """Stores which agent message created or updated a condition."""

    __tablename__ = "agent_condition_writes"

    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "thesis_id", "user_id"],
            [
                "agent_sessions.id",
                "agent_sessions.thesis_id",
                "agent_sessions.user_id",
            ],
            name="agent_condition_write_session_chain",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["message_id", "session_id", "user_id"],
            [
                "agent_messages.id",
                "agent_messages.session_id",
                "agent_messages.user_id",
            ],
            name="agent_condition_write_message_chain",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["condition_id", "thesis_id", "user_id"],
            [
                "thesis_conditions.id",
                "thesis_conditions.thesis_id",
                "thesis_conditions.user_id",
            ],
            name="agent_condition_write_condition_chain",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_agent_condition_writes_condition",
            "condition_id",
            "created_at",
        ),
        CheckConstraint(
            "action IN ('create', 'update')",
            name="action_valid",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    message_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
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
    action: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )