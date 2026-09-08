from types import TracebackType
from typing import Self

import httpx

from app.data_sources.base import OutputSize, StockDataSource
from app.data_sources.finnhub_client import FinnhubClient
from app.data_sources.finnhub_parser import parse_finnhub_daily, parse_finnhub_fundamentals
from app.data_sources.fundamental_models import CompanyFundamentals
from app.data_sources.models import DailyBar
from app.data_sources.settings import DataSourceSettings


class FinnhubAdapter(StockDataSource):
    """Adapter that maps the Finnhub HTTP client onto ``StockDataSource``."""

    def __init__(
        self,
        settings: DataSourceSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = FinnhubClient(
            settings=settings,
            http_client=http_client,
        )

    async def __aenter__(self) -> Self:
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._client.__aexit__(exc_type, exc_value, traceback)

    async def get_daily_bars(
        self,
        symbol: str,
        output_size: OutputSize = "compact",
    ) -> list[DailyBar]:
        normalized_symbol = FinnhubClient.normalize_symbol(symbol)
        payload = await self._client.fetch_daily_raw(
            symbol=normalized_symbol,
            output_size=output_size,
        )
        return parse_finnhub_daily(normalized_symbol, payload, output_size)

    async def get_company_fundamentals(self, symbol: str) -> CompanyFundamentals:
        normalized_symbol = FinnhubClient.normalize_symbol(symbol)
        payload = await self._client.fetch_metrics_raw(normalized_symbol)
        return parse_finnhub_fundamentals(normalized_symbol, payload)
