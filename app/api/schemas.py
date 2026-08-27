from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.data_sources.models import PriceAdjustment
from app.domain.event_models import (
    EventSeverity,
    EventStatus,
    EvidenceType,
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