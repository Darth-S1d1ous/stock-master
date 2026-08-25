from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

class CompanyFundamentals(BaseModel):
    """ company fundamentals """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    observation_id: UUID | None = Field(
        default=None,
        description="Stable identifier assigned after persistence",
    )
    snapshot_date: date | None = Field(
        default=None,
        description="Business date assigned when the snapshot is persisted",
    )
    symbol: str = Field(
        min_length=1,
        max_length=15,
        pattern=r"^[A-Z][A-Z0-9.-]*$",
        description="normalized us stock symbol, e.g. AAPL, GOOG, etc.",
    )

    latest_quarter: date | None = Field(default=None, description="latest quater for which fundamentals are available")

    """
    Allow fundamental fields to be none because there might be 
    {
    "PERatio": "None",
    "PriceToBookRatio": "-",
    "EBITDA": "None"
    }
    in real data
    """
    pe_ratio: Decimal | None = Field(default=None, description="price to earnings ratio")
    price_to_book_ratio: Decimal | None = Field(default=None, description="price to book ratio")
    ebitda: Decimal | None = Field(default=None, description="earnings before interest, taxes, depreciation, and amortization")

    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    source: str = Field(
        default="alpha_vantage",
        min_length=1,
        max_length=50,
    )
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator(
        "pe_ratio",
        "price_to_book_ratio",
        "ebitda",
    )
    @classmethod
    def require_finite_decimal(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("Value must be a finite decimal number")
        return value

    @field_validator("received_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Received datetime must be timezone-aware")
        return value