from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.thesis_models import ComparisonOperator, MetricCode

class EventSeverity(StrEnum):
    """Severity of an event."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class EventStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"

class EvidenceType(StrEnum):
    METRIC_OBSERVATION = "metric_observation"
    MARKET_DATA = "market_data"
    CALCULATION = "calculation"
    SOURCE_DOCUMENT = "source_document"

class FeedbackType(StrEnum):
    """User classifications recorded as an append-only feedback history."""

    USEFUL = "useful"
    NOT_USEFUL = "not_useful"
    FALSE_POSITIVE = "false_positive"
    CONFIRMED = "confirmed"
    IGNORED = "ignored"
    DUPLICATE = "duplicate"
    NOT_RELEVANT = "not_relevant"

class RuleEvaluation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    id: UUID = Field(default_factory=uuid4)

    user_id: UUID
    thesis_id: UUID
    condition_id: UUID

    symbol: str = Field(min_length=1, max_length=15, pattern=r"^[A-Z][A-Z0-9.-]*$")

    metric: MetricCode
    operator: ComparisonOperator

    observed_value: Decimal
    threshold: Decimal
    matched: bool

    consecutive_periods_required: int = Field(default=1, ge=1, le=12)
    consecutive_periods_matched: int = Field(default=0, ge=0, le=12)

    rule_version: int = Field(ge=1)

    data_as_of: date
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    observation_ids: tuple[UUID, ...] = Field(
        min_length=1,
        description="The normalized data record IDs for audit and event replay",
    )

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("observed_value", "threshold")
    @classmethod
    def require_finite_decimal(
        cls,
        value: Decimal,
    ) -> Decimal:
        if not value.is_finite():
            raise ValueError("Decimal must be finite")
        return value

    @field_validator("evaluated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_consecutive_periods(
        self,
    ) -> "RuleEvaluation":
        if (
            self.consecutive_periods_matched
            > self.consecutive_periods_required
        ):
            raise ValueError("consecutive_periods_matched cannot be greater than consecutive_periods_required")

        expected_match = (
            self.consecutive_periods_matched
            >= self.consecutive_periods_required
        )

        if self.matched != expected_match:
            raise ValueError("matched must be True if consecutive_periods_matched is greater than or equal to consecutive_periods_required")
        return self

class DomainEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    id : UUID = Field(default_factory=uuid4)

    user_id: UUID
    
    # DomainEvent
    # ├── belongs to InvestmentThesis
    # ├── triggered by ThesisCondition
    # └── created from RuleEvaluation
    thesis_id: UUID
    condition_id: UUID
    evaluation_id: UUID

    symbol: str = Field(min_length=1, max_length=15, pattern=r"^[A-Z][A-Z0-9.-]*$")

    event_type: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    severity: EventSeverity
    status: EventStatus = EventStatus.OPEN

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)

    occurred_on: date
    detected_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    rule_version: int = Field(ge=1)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("detected_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("detected_at must be timezone-aware")
        return value

class EventEvidence(BaseModel):
    """Auditable evidence supporting a domain event."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    id: UUID = Field(default_factory=uuid4)
    event_id: UUID
    user_id: UUID

    evidence_type: EvidenceType
    source: str = Field(
        min_length=1,
        max_length=50,
    )

    source_record_id: UUID | None = Field(
        default=None,
        description=("The related raw data, normalized observation, or document record ID"),
    )
    source_reference: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "A provider record number, document identifier, or data field reference; "
            "this value is for display and auditing only and must not be used directly as a request URL"
        ),
    )

    metric: MetricCode | None = None
    observed_value: Decimal | None = None

    description: str = Field(
        min_length=1,
        max_length=2000,
    )
    excerpt: str | None = Field(
        default=None,
        max_length=5000,
    )

    data_as_of: date | None = None
    published_at: datetime | None = None
    observed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

    @field_validator("observed_value")
    @classmethod
    def require_finite_value(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError(
                "Evidence values must not be NaN or infinite"
            )
        return value

    @field_validator("published_at", "observed_at")
    @classmethod
    def require_timezone(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if (
            value is not None
            and (
                value.tzinfo is None
                or value.utcoffset() is None
            )
        ):
            raise ValueError("Evidence timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_metric_evidence(self) -> "EventEvidence":
        metric_evidence_types = {
            EvidenceType.METRIC_OBSERVATION,
            EvidenceType.MARKET_DATA,
            EvidenceType.CALCULATION,
        }

        if self.evidence_type in metric_evidence_types:
            if self.metric is None:
                raise ValueError(
                    "Numeric evidence must specify metric"
                )

            if self.observed_value is None:
                raise ValueError(
                    "Numeric evidence must specify observed_value"
                )

        if (
            self.published_at is not None
            and self.published_at > self.observed_at
        ):
            raise ValueError(
                "published_at must not be later than observed_at"
            )

        return self


class EventFeedback(BaseModel):
    """One immutable entry in a user's append-only event feedback history."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    id: UUID = Field(default_factory=uuid4)

    event_id: UUID
    user_id: UUID

    feedback_type: FeedbackType
    comment: str | None = Field(
        default=None,
        max_length=2000,
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value