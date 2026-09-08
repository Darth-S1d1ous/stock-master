from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from app.data_sources.base import OutputSize
from app.data_sources.finnhub_client import FinnhubError
from app.data_sources.fundamental_models import CompanyFundamentals
from app.data_sources.models import DailyBar, PriceAdjustment


def parse_finnhub_daily(
    symbol: str,
    payload: Mapping[str, object],
    output_size: OutputSize,
) -> list[DailyBar]:
    status = payload.get("s")
    if status == "no_data":
        raise FinnhubError(f"Finnhub returned no daily bars: {symbol}")
    if status != "ok":
        raise FinnhubError("Finnhub daily-bar status is invalid")

    opens = _require_sequence(payload, "o")
    highs = _require_sequence(payload, "h")
    lows = _require_sequence(payload, "l")
    closes = _require_sequence(payload, "c")
    volumes = _require_sequence(payload, "v")
    timestamps = _require_sequence(payload, "t")
    arrays = (opens, highs, lows, closes, volumes, timestamps)
    lengths = {len(values) for values in arrays}
    if len(lengths) != 1 or lengths == {0}:
        raise FinnhubError("Finnhub daily-bar arrays are empty or have inconsistent lengths")

    received_at = datetime.now(UTC)
    bars: list[DailyBar] = []
    try:
        for index in range(len(opens)):
            bars.append(
                DailyBar(
                    symbol=symbol,
                    trading_date=datetime.fromtimestamp(
                        int(str(timestamps[index])), tz=UTC
                    ).date(),
                    open=_to_decimal(opens[index]),
                    high=_to_decimal(highs[index]),
                    low=_to_decimal(lows[index]),
                    close=_to_decimal(closes[index]),
                    volume=_to_volume(volumes[index]),
                    currency="USD",
                    adjustment=PriceAdjustment.RAW,
                    source="finnhub",
                    received_at=received_at,
                )
            )
    except (InvalidOperation, TypeError, ValueError, ValidationError) as exc:
        raise FinnhubError(f"Finnhub daily-bar parsing failed: {symbol}") from exc

    bars.sort(key=lambda bar: bar.trading_date)
    return bars[-100:] if output_size == "compact" else bars


def parse_finnhub_fundamentals(
    symbol: str,
    payload: Mapping[str, object],
) -> CompanyFundamentals:
    metric = payload.get("metric")
    if not isinstance(metric, Mapping):
        raise FinnhubError("Finnhub fundamentals response is missing metric")

    try:
        return CompanyFundamentals(
            symbol=symbol,
            latest_quarter=_latest_period(payload.get("series")),
            pe_ratio=_first_decimal(metric, "peTTM", "peBasicExclExtraTTM"),
            price_to_book_ratio=_first_decimal(metric, "pbQuarterly", "pbAnnual"),
            ebitda=_first_decimal(metric, "ebitda", "ebitdaTTM", "ebitdTTM"),
            currency="USD",
            source="finnhub",
            received_at=datetime.now(UTC),
        )
    except (ValueError, ValidationError) as exc:
        raise FinnhubError(f"Finnhub fundamentals parsing failed: {symbol}") from exc


def _latest_period(value: object) -> date | None:
    if not isinstance(value, Mapping):
        return None
    candidates: list[date] = []
    for group in value.values():
        if not isinstance(group, Mapping):
            continue
        for records in group.values():
            if not isinstance(records, Sequence):
                continue
            for record in records:
                if not isinstance(record, Mapping):
                    continue
                period = record.get("period")
                if isinstance(period, str):
                    try:
                        candidates.append(date.fromisoformat(period[:10]))
                    except ValueError:
                        continue
    return max(candidates) if candidates else None


def _first_decimal(
    payload: Mapping[str, object],
    *keys: str,
) -> Decimal | None:
    for key in keys:
        value = payload.get(key)
        if value is None or value == "":
            continue
        parsed = _to_decimal(value)
        if parsed.is_finite():
            return parsed
    return None


def _require_sequence(
    payload: Mapping[str, object],
    key: str,
) -> Sequence[object]:
    value = payload.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise FinnhubError(f"Finnhub daily-bar field {key!r} is not an array")
    return value


def _to_decimal(value: object) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid numeric value: {value!r}") from exc
    if not parsed.is_finite():
        raise ValueError(f"Numeric value must be finite: {value!r}")
    return parsed


def _to_volume(value: object) -> int:
    parsed = _to_decimal(value)
    if parsed < 0 or parsed != parsed.to_integral_value():
        raise ValueError(f"Invalid volume: {value!r}")
    return int(parsed)
