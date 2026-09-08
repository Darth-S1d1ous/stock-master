from abc import ABC, abstractmethod
from types import TracebackType
from typing import Literal, Self

from app.data_sources.fundamental_models import CompanyFundamentals
from app.data_sources.models import DailyBar

OutputSize = Literal["compact", "full"]


class StockDataSource(ABC):
    """Target interface for market-data adapters.

    Application code depends only on this contract. Each provider-specific
    adapter translates a third-party API (the adaptee) into this shape.
    """

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    @abstractmethod
    async def get_daily_bars(
        self,
        symbol: str,
        output_size: OutputSize = "compact",
    ) -> list[DailyBar]:
        """Return normalized daily OHLCV bars for ``symbol``."""

    @abstractmethod
    async def get_company_fundamentals(
        self,
        symbol: str,
    ) -> CompanyFundamentals:
        """Return a normalized fundamental snapshot for ``symbol``."""
