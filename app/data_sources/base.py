from types import TracebackType
from typing import Literal, Protocol, Self

from app.data_sources.fundamental_models import CompanyFundamentals
from app.data_sources.models import DailyBar


OutputSize = Literal["compact", "full"]


class StockDataSource(Protocol):
    """所有股票数据源对业务层暴露的统一契约。"""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def get_daily_bars(
        self,
        symbol: str,
        output_size: OutputSize = "compact",
    ) -> list[DailyBar]: ...

    async def get_company_fundamentals(
        self,
        symbol: str,
    ) -> CompanyFundamentals: ...
