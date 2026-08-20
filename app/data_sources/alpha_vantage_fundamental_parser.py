from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Final

from pydantic import ValidationError

from app.data_sources.fundamental_models import CompanyFundamentals

_SYMBOL_KEY: Final = "Symbol"
_LATEST_QUARTER_KEY: Final = "LatestQuarter"
_PE_RATIO_KEY: Final = "PERatio"
_PRICE_TO_BOOK_KEY: Final = "PriceToBookRatio"
_EBITDA_KEY: Final = "EBITDA"
_CURRENCY_KEY: Final = "Currency"

_MISSING_VALUES: Final = frozenset(
    {
        "",
        "-",
        "--",
        "none",
        "null",
        "n/a",
        "na",
        "nan",
    }
)

class AlphaVantageFundamentalParseError(ValueError):
    """ Alpha Vantage response cannot be parsed into CompanyFundamentals model """

""" provided api for obtaining company fundamentals """
def parse_alpha_vantage_company_overview(payload: Mapping[str, object]) -> CompanyFundamentals:
    symbol = _require_string(payload, _SYMBOL_KEY).strip().upper()

    latest_quarter = _parse_optional_date(
        payload.get(_LATEST_QUARTER_KEY),
        _LATEST_QUARTER_KEY,
    )
    pe_ratio = _parse_optional_decimal(
        payload.get(_PE_RATIO_KEY),
        _PE_RATIO_KEY,
    )
    price_to_book_ratio = _parse_optional_decimal(
        payload.get(_PRICE_TO_BOOK_KEY),
        _PRICE_TO_BOOK_KEY,
    )
    ebitda = _parse_optional_decimal(
        payload.get(_EBITDA_KEY),
        _EBITDA_KEY,
    )

    currency = _parse_currency(payload.get(_CURRENCY_KEY))

    try:
        return CompanyFundamentals(
            symbol=symbol,
            latest_quarter=latest_quarter,
            pe_ratio=pe_ratio,
            price_to_book_ratio=price_to_book_ratio,
            ebitda=ebitda,
            currency=currency,
            source="alpha_vantage",
            received_at=datetime.now(UTC),
        )
    except ValidationError as exc:
        raise AlphaVantageFundamentalParseError(f"Invalid company overview data: {payload}") from exc

def _require_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise AlphaVantageFundamentalParseError(f"Expected a string for {key}, got {type(value)}")

    return value

def _parse_optional_decimal(value: object, key: str) -> Decimal | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise AlphaVantageFundamentalParseError(f"Expected a string or None for {key}, got {type(value)}")

    normalized = value.strip()
    if normalized.lower() in _MISSING_VALUES:
        return None

    try:
        parsed = Decimal(normalized)
    except InvalidOperation as exc:
        raise AlphaVantageFundamentalParseError(f"Invalid decimal value for {key}: {value}") from exc

    if not parsed.is_finite():
        raise AlphaVantageFundamentalParseError(f"Invalid decimal value for {key}: {value}")

    return parsed

def _parse_optional_date(value: object, key: str) -> date | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise AlphaVantageFundamentalParseError(f"Expected a string or None for {key}, got {type(value)}")

    normalized = value.strip()
    if normalized.lower() in _MISSING_VALUES:
        return None

    try:
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise AlphaVantageFundamentalParseError(f"Invalid date value for {key}: {value}. Require YYYY-MM-DD format.") from exc

def _parse_currency(value: object) -> str:
    if value is None:
        return "USD"

    if not isinstance(value, str):
        raise AlphaVantageFundamentalParseError(f"Expected a string or None for Currency, got {type(value)}")

    normalized = value.strip().upper()
    if normalized.lower() in _MISSING_VALUES:
        return "USD"

    return normalized