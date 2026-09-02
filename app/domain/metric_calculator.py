from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.data_sources.fundamental_models import CompanyFundamentals
from app.data_sources.models import DailyBar
from app.domain.thesis_models import MetricCode

_ONE_HUNDRED = Decimal(100)
_VOLUME_WINDOW = 20


class MetricCalculationError(ValueError):
    """Raised when a metric cannot be calculated from the supplied data."""


class MetricResult(BaseModel):
    """A deterministic metric value and its complete audit references."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    metric: MetricCode
    value: Decimal
    data_as_of: date
    observation_ids: tuple[UUID, ...] = Field(min_length=1)
    calculation_version: int = Field(default=1, ge=1)

    @field_validator("value")
    @classmethod
    def require_finite_value(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Metric value must be finite")
        return value

    @field_validator("observation_ids")
    @classmethod
    def require_unique_observation_ids(
        cls,
        value: tuple[UUID, ...],
    ) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("observation_ids must be unique")
        return value


def calculate_daily_price_change_percent(
    bars: Sequence[DailyBar],
) -> MetricResult:
    """Calculate close-to-close percentage change for the latest trading day."""

    ordered = _prepare_daily_bars(bars, minimum=2)
    previous, current = ordered[-2:]

    value = _percentage_change(
        current=current.close,
        previous=previous.close,
        metric_name=MetricCode.DAILY_PRICE_CHANGE_PERCENT,
    )

    return MetricResult(
        metric=MetricCode.DAILY_PRICE_CHANGE_PERCENT,
        value=value,
        data_as_of=current.trading_date,
        observation_ids=(
            _require_observation_id(previous),
            _require_observation_id(current),
        ),
    )


def calculate_volume_ratio_20d(
    bars: Sequence[DailyBar],
) -> MetricResult:
    """Calculate latest volume divided by the prior 20 trading-day average."""

    ordered = _prepare_daily_bars(
        bars,
        minimum=_VOLUME_WINDOW + 1,
    )
    history = ordered[-(_VOLUME_WINDOW + 1):-1]
    current = ordered[-1]

    average_volume = (
        sum((Decimal(bar.volume) for bar in history), Decimal(0))
        / Decimal(_VOLUME_WINDOW)
    )
    if average_volume == 0:
        raise MetricCalculationError(
            "VOLUME_RATIO_20D cannot be calculated when the prior average volume is zero"
        )

    return MetricResult(
        metric=MetricCode.VOLUME_RATIO_20D,
        value=Decimal(current.volume) / average_volume,
        data_as_of=current.trading_date,
        observation_ids=tuple(
            _require_observation_id(bar)
            for bar in (*history, current)
        ),
    )


def calculate_pe_ratio(
    snapshots: Sequence[CompanyFundamentals],
) -> MetricResult:
    """Return the latest available PE ratio."""

    return _calculate_current_fundamental(
        snapshots=snapshots,
        metric=MetricCode.PE_RATIO,
        selector=lambda item: item.pe_ratio,
    )


def calculate_pe_ratio_change_percent(
    snapshots: Sequence[CompanyFundamentals],
) -> MetricResult:
    """Calculate the percentage change between the latest two available PE ratios."""

    return _calculate_fundamental_change(
        snapshots=snapshots,
        metric=MetricCode.PE_RATIO_CHANGE_PERCENT,
        selector=lambda item: item.pe_ratio,
    )


def calculate_price_to_book_ratio(
    snapshots: Sequence[CompanyFundamentals],
) -> MetricResult:
    """Return the latest available price-to-book ratio."""

    return _calculate_current_fundamental(
        snapshots=snapshots,
        metric=MetricCode.PRICE_TO_BOOK_RATIO,
        selector=lambda item: item.price_to_book_ratio,
    )


def calculate_price_to_book_change_percent(
    snapshots: Sequence[CompanyFundamentals],
) -> MetricResult:
    """Calculate the percentage change between the latest two available PB ratios."""

    return _calculate_fundamental_change(
        snapshots=snapshots,
        metric=MetricCode.PRICE_TO_BOOK_CHANGE_PERCENT,
        selector=lambda item: item.price_to_book_ratio,
    )


def calculate_ebitda(
    snapshots: Sequence[CompanyFundamentals],
) -> MetricResult:
    """Return the latest available EBITDA value."""

    return _calculate_current_fundamental(
        snapshots=snapshots,
        metric=MetricCode.EBITDA,
        selector=lambda item: item.ebitda,
    )


def _calculate_current_fundamental(
    snapshots: Sequence[CompanyFundamentals],
    metric: MetricCode,
    selector: Callable[[CompanyFundamentals], Decimal | None],
) -> MetricResult:
    ordered = _prepare_fundamentals(snapshots)

    for snapshot in reversed(ordered):
        value = selector(snapshot)
        if value is not None:
            return MetricResult(
                metric=metric,
                value=value,
                data_as_of=_fundamental_data_as_of(snapshot),
                observation_ids=(
                    _require_observation_id(snapshot),
                ),
            )

    raise MetricCalculationError(
        f"{metric.value} is unavailable in all supplied snapshots"
    )


def _calculate_fundamental_change(
    snapshots: Sequence[CompanyFundamentals],
    metric: MetricCode,
    selector: Callable[[CompanyFundamentals], Decimal | None],
) -> MetricResult:
    ordered = _prepare_fundamentals(snapshots)
    available = [
        (snapshot, value)
        for snapshot in ordered
        if (value := selector(snapshot)) is not None
    ]

    if len(available) < 2:
        raise MetricCalculationError(
            f"{metric.value} requires at least two snapshots with values"
        )

    previous_snapshot, previous_value = available[-2]
    current_snapshot, current_value = available[-1]
    value = _percentage_change(
        current=current_value,
        previous=previous_value,
        metric_name=metric,
    )

    return MetricResult(
        metric=metric,
        value=value,
        data_as_of=_fundamental_data_as_of(current_snapshot),
        observation_ids=(
            _require_observation_id(previous_snapshot),
            _require_observation_id(current_snapshot),
        ),
    )


def _prepare_daily_bars(
    bars: Sequence[DailyBar],
    minimum: int,
) -> list[DailyBar]:
    if len(bars) < minimum:
        raise MetricCalculationError(
            f"At least {minimum} daily bars are required"
        )

    ordered = sorted(bars, key=lambda item: item.trading_date)
    series_keys = {
        (item.symbol, item.source, item.adjustment)
        for item in ordered
    }
    if len(series_keys) != 1:
        raise MetricCalculationError(
            "All daily bars must belong to the same symbol and source series"
        )

    dates = [bar.trading_date for bar in ordered]
    if len(dates) != len(set(dates)):
        raise MetricCalculationError(
            "Daily bars must contain one observation per trading date"
        )

    return ordered


def _prepare_fundamentals(
    snapshots: Sequence[CompanyFundamentals],
) -> list[CompanyFundamentals]:
    if not snapshots:
        raise MetricCalculationError(
            "At least one fundamental snapshot is required"
        )

    ordered = sorted(
        snapshots,
        key=lambda item: (
            _fundamental_data_as_of(item),
            item.received_at,
        ),
    )
    series_keys = {
        (item.symbol, item.source)
        for item in ordered
    }
    if len(series_keys) != 1:
        raise MetricCalculationError(
            "All fundamental snapshots must belong to the same symbol and source series"
        )
    dates = [_fundamental_data_as_of(item) for item in ordered]
    if len(dates) != len(set(dates)):
        raise MetricCalculationError(
            "Fundamental snapshots must contain one observation per snapshot date"
        )
    return ordered


def _fundamental_data_as_of(snapshot: CompanyFundamentals) -> date:
    return snapshot.snapshot_date or snapshot.received_at.date()


def _percentage_change(
    current: Decimal,
    previous: Decimal,
    metric_name: MetricCode,
) -> Decimal:
    if previous == 0:
        raise MetricCalculationError(
            f"{metric_name.value} cannot be calculated from a zero previous value"
        )
    return ((current - previous) / previous) * _ONE_HUNDRED


def _require_observation_id(
    value: DailyBar | CompanyFundamentals,
) -> UUID:
    if value.observation_id is None:
        raise MetricCalculationError(
            "Metrics used for rule evaluation require persisted observations"
        )
    return value.observation_id
