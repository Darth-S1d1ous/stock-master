from datetime import UTC, datetime
from enum import Enum, StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class AgentSessionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"

class AgentMessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

class AgentConditionWriteAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"

# TODO: will have more session types, should this be a shared session?
class AgentSession(BaseModel):
    """One condition-authoring conversation scoped to a saved thesis."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    thesis_id: UUID
    symbol: str = Field(min_length=1, max_length=15, pattern=r"^[A-Z][A-Z0-9.-]*$")
    status: AgentSessionStatus = AgentSessionStatus.OPEN
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value
    
    @field_validator("created_at", "updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_timestamps(self) -> "AgentSession":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be after created_at")
        return self

# TODO: context window is limited, any truncation methods? Otherwise this shouldn't be very long
class AgentMessage(BaseModel):
    """One append-only turn in an agent session. This is working memory."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    user_id: UUID
    role: AgentMessageRole
    content: str = Field(min_length=1, max_length=20000)
    tool_name: str | None = Field(default=None, min_length=1, max_length=100)
    tool_call_id: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    prompt_version: str | None = Field(default=None, min_length=1, max_length=50)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    @model_validator(mode="after")
    def validate_role_fields(self) -> "AgentMessage":
        if self.role is AgentMessageRole.TOOL:
            if self.tool_name is None or self.tool_call_id is None:
                raise ValueError("tool messages require tool_name and tool_call_id")
            return self
        if self.tool_name is not None or self.tool_call_id is not None:
            raise ValueError("tool_name and tool_call_id are only valid on tool messages")
        if self.role is not AgentMessageRole.ASSISTANT:
            if self.model is not None or self.prompt_version is not None:
                raise ValueError("model and prompt_version are only valid on assistant messages")
        return self

class AgentMemory(BaseModel):
    """Rolling summary of a long session. Not a vector embedding."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    user_id: UUID
    summary: str = Field(min_length=1, max_length=8000)
    message_count_at_summary: int = Field(ge=1)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    @field_validator("updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value

class AgentConditionWrite(BaseModel):
    """Audit link: which agent turn created or updated a condition."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    message_id: UUID
    user_id: UUID
    thesis_id: UUID
    condition_id: UUID
    action: AgentConditionWriteAction
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value