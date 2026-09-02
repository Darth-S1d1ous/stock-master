from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ThesisStatus(StrEnum):
    ACTIVE = "active"
    CHALLENGED = "challenged"
    INVALIDATED = "invalidated"
    ARCHIVED = "archived"

class ConditionKind(StrEnum):
    SUPPORT = "support"
    RISK = "risk"
    INVALIDATION = "invalidation"

class MetricCode(StrEnum):
    """ normalized metrics """
    DAILY_PRICE_CHANGE_PERCENT = "daily_price_change_percent"
    VOLUME_RATIO_20D = "volume_ratio_20d"
    PE_RATIO = "pe_ratio"
    PE_RATIO_CHANGE_PERCENT = "pe_ratio_change_percent"
    PRICE_TO_BOOK_RATIO = "price_to_book_ratio"
    PRICE_TO_BOOK_CHANGE_PERCENT = (
        "price_to_book_change_percent"
    )
    EBITDA = "ebitda"

class ComparisonOperator(StrEnum):
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"

class InvestmentThesis(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID

    symbol: str = Field(min_length=1, max_length=15, pattern=r"^[A-Z][A-Z0-9.-]*$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)

    status: ThesisStatus = ThesisStatus.ACTIVE
    version: int = Field(default=1, ge=1)

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
    def validate_timestamps(self) -> "InvestmentThesis":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be after created_at")
        return self

class ThesisStatusChange(BaseModel):
    """One immutable transition in an investment thesis lifecycle."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    id: UUID = Field(default_factory=uuid4)
    thesis_id: UUID
    user_id: UUID
    from_status: ThesisStatus
    to_status: ThesisStatus
    reason: str = Field(min_length=1, max_length=500)
    triggering_event_id: UUID | None = None
    changed_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    @field_validator("changed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("changed_at must be timezone-aware")
        return value


class ThesisCondition(BaseModel):
    """ investment thesis condition that can be deterministically determined by code """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    id: UUID = Field(default_factory=uuid4)
    thesis_id: UUID
    user_id: UUID

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

    kind: ConditionKind
    metric: MetricCode
    operator: ComparisonOperator
    threshold: Decimal

    consecutive_periods: int = Field(
        default=1,
        ge=1,
        le=12,
        description="number of consecutive periods that must meet the condition",
    )

    enabled: bool = True
    version: int = Field(default=1, ge=1)

    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    @field_validator("threshold")
    @classmethod
    def require_finite_threshold(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("threshold must be finite")
        return value 

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_timestamps(self) -> "ThesisCondition":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be after created_at")
        return self