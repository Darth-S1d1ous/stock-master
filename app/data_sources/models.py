from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PriceAdjustment(StrEnum):
    RAW = "raw"
    SPLIT_ADJUSTED = "split_adjusted"
    TOTAL_RETURN = "total_return"

class DailyBar(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    observation_id: UUID | None = Field(
        default=None,
        description="Stable identifier assigned after persistence",
    )
    symbol: str = Field(
        min_length=1,
        max_length=15,
        pattern=r"^[A-Z][A-Z0-9.-]*$",
        description="Stock symbol, e.g. AAPL, GOOG, etc.",
    )

    trading_date: date

    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: int = Field(ge=0)

    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    adjustment: PriceAdjustment = PriceAdjustment.RAW

    source: str = Field(min_length=1, max_length=50)
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

    @field_validator("received_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Received datetime must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_price_range(self) -> "DailyBar":
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("High price must be greater than or equal to open, close, and low prices")
        
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("Low price must be less than or equal to open, close, and high prices")

        return self