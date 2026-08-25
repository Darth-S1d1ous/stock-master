"""
bind each metric to its required data fields and the calculator function, and provide a metric calculator entry
solves the problem that ThesisMonotoring should not directly maintain a large amount of if/elif branches 
"""
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from app.data_sources.fundamental_models import CompanyFundamentals
from app.data_sources.models import DailyBar
from app.domain.metric_calculator import (
    MetricResult,
    calculate_daily_price_change_percent,
    calculate_ebitda,
    calculate_pe_ratio,
    calculate_pe_ratio_change_percent,
    calculate_price_to_book_change_percent,
    calculate_price_to_book_ratio,
    calculate_volume_ratio_20d,
)
from app.domain.thesis_models import MetricCode

DailyMetricCalculator = Callable[[Sequence[DailyBar]], MetricResult]
FundamentalMetricCalculator = Callable[[Sequence[CompanyFundamentals]], MetricResult]

class MetricRegistryError(ValueError):
    """Raised when metric registration or dispatch is invalid."""


class MetricInputKind(StrEnum):
    """The persisted observation family required by a metric."""

    DAILY_BARS = "daily_bars"
    FUNDAMENTALS = "fundamentals"

@dataclass(fronzen=True, slots=True)
class MetricDefinition:
    """Static calculation requirements for one deterministic metric."""
    
    metric: MetricCode
    input_kind: MetricInputKind
    required_observations: int
    daily_calculator: DailyMetricCalculator | None = field(default=None, repr=False)
    fundamental_calculator: FundamentalMetricCalculator | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.required_observations < 1:
            raise MetricRegistryError("required_observations must be at least one")

        if self.input_kind is MetricInputKind.DAILY_BARS:
            if self.daily_calculator is None:
                raise MetricRegistryError(f"{self.metric.value} requires a daily-bar calculator")
            if self.fundamental_calculator is not None:
                raise MetricRegistryError(f"{self.metric.value} cannot also define a fundamental calculator")
            return

        if self.input_kind is MetricInputKind.FUNDAMENTALS:
            if self.fundamental_calculator is None:
                raise MetricRegistryError(f"{self.metric.value} requires a fundamental calculator")
            if self.daily_calculator is not None:
                raise MetricRegistryError(f"{self.metric.value} cannot also define a daily-bar calculator")
            return
        
        raise MetricRegistryError(f"Unsupported metric input kind: {self.input_kind}")

    def calculate_daily(self, bars: Sequence[DailyBar]) -> MetricResult:
        """Calculate this metric from persisted daily bars."""
        if self.input_kind is not MetricInputKind.DAILY_BARS:
            raise MetricRegistryError(
                f"{self.metric.value} cannot be calculated "
                "from daily bars"
            )

        if len(bars) < self.required_observations:
            raise MetricRegistryError(
                f"{self.metric.value} requires at least "
                f"{self.required_observations} daily bars"
            )

        calculator = self.daily_calculator
        if calculator is None:
            raise MetricRegistryError(
                f"{self.metric.value} has no daily-bar calculator"
            )

        result = calculator(bars)
        self._validate_result(result)
        return result

    def calculate_fundamentals(
        self,
        snapshots: Sequence[CompanyFundamentals],
    ) -> MetricResult:
        """Calculate this metric from persisted fundamental snapshots."""

        if self.input_kind is not MetricInputKind.FUNDAMENTALS:
            raise MetricRegistryError(
                f"{self.metric.value} cannot be calculated "
                "from fundamental snapshots"
            )

        if len(snapshots) < self.required_observations:
            raise MetricRegistryError(
                f"{self.metric.value} requires at least "
                f"{self.required_observations} fundamental snapshots"
            )

        calculator = self.fundamental_calculator
        if calculator is None:
            raise MetricRegistryError(f"{self.metric.value} has no fundamental calculator")

        result = calculator(snapshots)
        self._validate_result(result)
        return result

    def _validate_result(
        self,
        result: MetricResult,
    ) -> None:
        if result.metric is not self.metric:
            raise MetricRegistryError(
                f"Calculator registered for {self.metric.value} "
                f"returned {result.metric.value}"
            )

_METRIC_DEFINITIONS = (
    MetricDefinition(
        metric=MetricCode.DAILY_PRICE_CHANGE_PERCENT,
        input_kind=MetricInputKind.DAILY_BARS,
        required_observations=2,
        daily_calculator=calculate_daily_price_change_percent,
    ),
    MetricDefinition(
        metric=MetricCode.VOLUME_RATIO_20D,
        input_kind=MetricInputKind.DAILY_BARS,
        required_observations=21,
        daily_calculator=calculate_volume_ratio_20d,
    ),
    MetricDefinition(
        metric=MetricCode.PE_RATIO,
        input_kind=MetricInputKind.FUNDAMENTALS,
        required_observations=1,
        fundamental_calculator=calculate_pe_ratio,
    ),
    MetricDefinition(
        metric=MetricCode.PE_RATIO_CHANGE_PERCENT,
        input_kind=MetricInputKind.FUNDAMENTALS,
        required_observations=2,
        fundamental_calculator=calculate_pe_ratio_change_percent,
    ),
    MetricDefinition(
        metric=MetricCode.PRICE_TO_BOOK_RATIO,
        input_kind=MetricInputKind.FUNDAMENTALS,
        required_observations=1,
        fundamental_calculator=calculate_price_to_book_ratio,
    ),
    MetricDefinition(
        metric=MetricCode.PRICE_TO_BOOK_CHANGE_PERCENT,
        input_kind=MetricInputKind.FUNDAMENTALS,
        required_observations=2,
        fundamental_calculator=(
            calculate_price_to_book_change_percent
        ),
    ),
    MetricDefinition(
        metric=MetricCode.EBITDA,
        input_kind=MetricInputKind.FUNDAMENTALS,
        required_observations=1,
        fundamental_calculator=calculate_ebitda,
    ),
)

def _build_registry(definitions: Sequence[MetricDefinition]) -> Mapping[MetricCode, MetricDefinition]:
    registry: dict[MetricCode, MetricDefinition] = {}

    for definition in definitions:
        if definition.metric in registry:
            raise MetricRegistryError(f"Duplicate metric definition: {definition.metric.value}")

        registry[definition.metric] = definition

    missing_metrics = set(MetricCode).difference(registry)
    if missing_metrics:
        missing_values = ", ".join(sorted(metric.value for metric in missing_metrics))
        raise MetricRegistryError(f"Metrics are missing from the registry: {missing_values}")

    # read-only view of the registry
    return MappingProxyType(registry)

METRIC_REGISTRY: Mapping[MetricCode, MetricDefinition] = (
    _build_registry(_METRIC_DEFINITIONS)
)

def get_metric_definition(metric: MetricCode) -> MetricDefinition:
    """Return the immutable definition for a supported metric."""
    try:
        return METRIC_REGISTRY[metric]
    except KeyError:
        raise MetricRegistryError(f"Unsupported metric: {metric}")

def calculate_daily_metric(metric: MetricCode, bars: Sequence[DailyBar]) -> MetricResult:
    """Resolve and calculate a metric backed by daily bars."""
    return get_metric_definition(metric).calculate_daily(bars)

def calculate_fundamental_metric(metric: MetricCode, snapshots: Sequence[CompanyFundamentals]) -> MetricResult:
    """Resolve and calculate a metric backed by fundamentals."""
    return get_metric_definition(metric).calculate_fundamentals(snapshots)