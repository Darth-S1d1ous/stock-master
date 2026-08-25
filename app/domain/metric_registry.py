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