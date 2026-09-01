from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.data_sources.models import PriceAdjustment
from app.domain.event_models import (
    EventSeverity,
    EventStatus,
    EvidenceType,
    FeedbackType,
)
from app.domain.thesis_models import (
    ComparisonOperator,
    ConditionKind,
    MetricCode,
    ThesisStatus,
)

class MarketDataSource(StrEnum):
    """Market-data providers supported by the public API."""

    ALPHA_VANTAGE = "alpha_vantage"
    FINNHUB = "finnhub"
    YAHOO_FINANCE = "yahoo_finance"

# Base classes
class ApiRequest(BaseModel):
    """Base configuration shared by API request schemas."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

class ApiResponse(BaseModel):
    """Base configuration shared by API response schemas."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        from_attributes=True,
    )

class CreateInvestmentThesisRequest(ApiRequest):
    """Request body for creating an investment thesis.

    Ownership, ID, version, status, and timestamps are assigned by the
    authenticated application layer and cannot be supplied by clients.
    """

    symbol: str = Field(
        min_length=1,
        max_length=15,
        pattern=r"^[A-Z][A-Z0-9.-]*$",
        examples=["AAPL"],
    )
    title: str = Field(
        min_length=1,
        max_length=200,
        examples=["Services growth remains durable"],
    )
    description: str = Field(
        min_length=1,
        max_length=5000,
        examples=["Services will remain a primary growth driver over the next three years."],
    )

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(
        cls,
        value: object,
    ) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

class UpdateInvestmentThesisRequest(ApiRequest):
    """Optimistic update for thesis content or lifecycle status."""

    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    status: ThesisStatus | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_change(self) -> "UpdateInvestmentThesisRequest":
        if self.title is None and self.description is None and self.status is None:
            raise ValueError("at least one thesis field must be changed")
        if self.status is not None and self.reason is None:
            raise ValueError("reason is required when status changes")
        return self


class InvestmentThesisResponse(ApiResponse):
    """Public representation of an investment thesis."""

    id: UUID
    symbol: str
    title: str
    description: str
    status: ThesisStatus
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime

class CreateThesisConditionRequest(ApiRequest):
    """Request body for adding a deterministic condition to a thesis.

    The thesis ID is obtained from the route path. The authenticated user
    ID, condition ID, version, and timestamps are assigned by the
    application layer.
    """

    name: str = Field(
        min_length=1,
        max_length=200,
        examples=["Daily price decline"],
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        examples=[
            "Create a risk event when the stock declines by at least five percent in one trading day."],
    )
    kind: ConditionKind
    metric: MetricCode
    operator: ComparisonOperator
    threshold: Decimal
    consecutive_periods: int = Field(
        default=1,
        ge=1,
        le=12,
    )
    enabled: bool = True

    @field_validator("threshold")
    @classmethod
    def require_finite_threshold(
        cls,
        value: Decimal,
    ) -> Decimal:
        if not value.is_finite():
            raise ValueError(
                "threshold must not be NaN or infinite"
            )
        return value

class UpdateThesisConditionRequest(ApiRequest):
    """Versioned update for a deterministic thesis condition."""

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    kind: ConditionKind | None = None
    metric: MetricCode | None = None
    operator: ComparisonOperator | None = None
    threshold: Decimal | None = None
    consecutive_periods: int | None = Field(default=None, ge=1, le=12)
    enabled: bool | None = None

    @field_validator("threshold")
    @classmethod
    def require_finite_threshold(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("threshold must not be NaN or infinite")
        return value

    @model_validator(mode="after")
    def require_change(self) -> "UpdateThesisConditionRequest":
        changed = self.model_fields_set.difference({"expected_version"})
        if not changed:
            raise ValueError("at least one condition field must be changed")
        return self


class ThesisConditionResponse(ApiResponse):
    """Public representation of a deterministic thesis condition."""

    id: UUID
    thesis_id: UUID
    name: str
    description: str | None
    kind: ConditionKind
    metric: MetricCode
    operator: ComparisonOperator
    threshold: Decimal
    consecutive_periods: int = Field(ge=1, le=12)
    enabled: bool
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime

class RunThesisMonitoringRequest(ApiRequest):
    """Request body for manually evaluating one investment thesis."""

    source: MarketDataSource
    adjustment: PriceAdjustment = PriceAdjustment.RAW

class MetricResultResponse(ApiResponse):
    """A deterministic metric calculated from persisted observations."""

    metric: MetricCode
    value: Decimal
    data_as_of: date
    observation_ids: tuple[UUID, ...] = Field(min_length=1)

class RuleEvaluationResponse(ApiResponse):
    """Public representation of one persisted rule evaluation."""

    id: UUID
    thesis_id: UUID
    condition_id: UUID
    symbol: str
    metric: MetricCode
    operator: ComparisonOperator
    observed_value: Decimal
    threshold: Decimal
    matched: bool
    consecutive_periods_required: int = Field(ge=1, le=12)
    consecutive_periods_matched: int = Field(ge=0, le=12)
    rule_version: int = Field(ge=1)
    data_as_of: date
    evaluated_at: datetime
    observation_ids: tuple[UUID, ...] = Field(min_length=1)

class DomainEventResponse(ApiResponse):
    """Public representation of a domain event."""

    id: UUID
    thesis_id: UUID
    condition_id: UUID
    evaluation_id: UUID
    symbol: str
    event_type: str
    severity: EventSeverity
    status: EventStatus
    title: str
    summary: str
    occurred_on: date
    detected_at: datetime
    rule_version: int = Field(ge=1)

class UpdateEventStatusRequest(ApiRequest):
    """Request body for changing an event workflow status."""

    status: EventStatus


class CreateEventFeedbackRequest(ApiRequest):
    """Request body for appending user feedback to an event."""

    feedback_type: FeedbackType
    comment: str | None = Field(default=None, max_length=2000)


class EventFeedbackResponse(ApiResponse):
    """Public representation of one immutable feedback entry."""

    id: UUID
    event_id: UUID
    feedback_type: FeedbackType
    comment: str | None
    created_at: datetime


class ThesisStatusHistoryResponse(ApiResponse):
    """Public representation of one thesis status transition."""

    id: UUID
    thesis_id: UUID
    from_status: ThesisStatus
    to_status: ThesisStatus
    reason: str
    triggering_event_id: UUID | None
    changed_at: datetime


class EventEvidenceResponse(ApiResponse):
    """Public representation of evidence supporting an event."""

    id: UUID
    event_id: UUID
    evidence_type: EvidenceType
    source: str
    source_record_id: UUID | None
    source_reference: str | None
    metric: MetricCode | None
    observed_value: Decimal | None
    description: str
    excerpt: str | None
    data_as_of: date | None
    published_at: datetime | None
    observed_at: datetime


class ConditionMonitoringResponse(ApiResponse):
    """Result of evaluating one enabled thesis condition."""

    condition: ThesisConditionResponse
    metric_result: MetricResultResponse
    evaluation: RuleEvaluationResponse
    event: DomainEventResponse | None
    evidence: tuple[EventEvidenceResponse, ...]
    reused_evaluation: bool = False


class ThesisMonitoringResponse(ApiResponse):
    """Result returned after manually evaluating an investment thesis."""

    thesis: InvestmentThesisResponse
    source: MarketDataSource
    started_at: datetime
    completed_at: datetime
    conditions: tuple[ConditionMonitoringResponse, ...]
    evaluation_count: int = Field(ge=0)
    matched_count: int = Field(ge=0)
    event_count: int = Field(ge=0)


class ErrorResponse(ApiResponse):
    """Stable error response returned by the HTTP API."""

    code: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_]*$",
        examples=["thesis_not_found"],
    )
    message: str = Field(
        min_length=1,
        max_length=500,
        examples=["Investment thesis was not found."],
    ) 