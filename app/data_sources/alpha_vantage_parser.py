from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Final

from pydantic import ValidationError

from app.data_sources.models import DailyBar, PriceAdjustment

_METADATA_KEY: Final = "Meta Data"
_TIME_SERIES_KEY: Final = "Time Series (Daily)"

_SYMBOL_KEY: Final = "2. Symbol"
_OPEN_KEY: Final = "1. open"
_HIGH_KEY: Final = "2. high"
_LOW_KEY: Final = "3. low"
_CLOSE_KEY: Final = "4. close"
_VOLUME_KEY: Final = "5. volume"

class AlphaVantageParseError(ValueError):
    """ Alpha Vantage response parsing error """

def parse_alpha_vantage_daily(payload: Mapping[str, object]) -> list[DailyBar]:
    """ return values are sorted in descending order by date """

    metadata = _require_mapping(payload, _METADATA_KEY)
    time_series = _require_mapping(payload, _TIME_SERIES_KEY)

    symbol = _require_string(metadata, _SYMBOL_KEY).strip().upper()
    received_at = datetime.now(UTC)

    bars: list[DailyBar] = []

    for trading_date, raw_bar in time_series.items():
        if not isinstance(trading_date, str):
            raise AlphaVantageParseError(f"Expected a string for trading date, got {type(trading_date)}")

        if not isinstance(raw_bar, Mapping):
            raise AlphaVantageParseError(f"Expected a mapping for raw bar, got {type(raw_bar)}")

        try:
            bar = DailyBar(
                symbol=symbol,
                trading_date=trading_date,
                open=_parse_decimal(raw_bar, _OPEN_KEY),
                high=_parse_decimal(raw_bar, _HIGH_KEY),
                low=_parse_decimal(raw_bar, _LOW_KEY),
                close=_parse_decimal(raw_bar, _CLOSE_KEY),
                volume=_parse_volume(raw_bar),
                currency="USD",
                adjustment=PriceAdjustment.RAW,
                source="alpha_vantage",
            )
        except ValidationError as exc:
            raise AlphaVantageParseError(f"Invalid bar data: {raw_bar}") from exc
    
        
        bars.append(bar)

    if not bars:
        raise AlphaVantageParseError("No bars found in response")

    bars.sort(key=lambda bar: bar.trading_date)
    return bars

def _require_mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key)

    if not isinstance(value, Mapping):
        raise AlphaVantageParseError(f"Expected a mapping for key '{key}', got {type(value)}")

    return value

def _require_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)

    if not isinstance(value, str) or not value.strip():
        raise AlphaVantageParseError(f"Expected a non-empty string for key '{key}', got {type(value)}")

    return value

def _parse_decimal(raw_bar: Mapping[str, object], key: str) -> Decimal:
    raw_value = _require_string(raw_bar, key)

    try:
        value = Decimal(raw_value)
    except InvalidOperation as exc:
        raise AlphaVantageParseError(f"{key!r} is not a valid decimal number") from exc

    if value <= 0:
        raise AlphaVantageParseError(f"Invalid decimal value for key '{key}': {raw_value} (must be greater than 0)")

    return value

def _parse_volume(raw_bar: Mapping[str, object]) -> int:
    raw_value = _require_string(raw_bar, _VOLUME_KEY)

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise AlphaVantageParseError(f"{_VOLUME_KEY!r} is not a valid integer") from exc

    if value < 0:
        raise AlphaVantageParseError(f"Invalid volume value: {raw_value} (must be greater than or equal to 0)")

    return value