from types import TracebackType
from typing import Self

import httpx

from app.data_sources.alpha_vantage_client import AlphaVantageClient
from app.data_sources.alpha_vantage_fundamental_parser import (
    parse_alpha_vantage_company_overview,
)
from app.data_sources.alpha_vantage_parser import parse_alpha_vantage_daily
from app.data_sources.base import OutputSize
from app.data_sources.fundamental_models import CompanyFundamentals
from app.data_sources.models import DailyBar
from app.data_sources.settings import DataSourceSettings


class AlphaVantageDataSource:
    """ Provides access to Alpha Vantage data source """

    def __init__(
        self,
        settings: DataSourceSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = AlphaVantageClient(
            settings=settings,
            http_client=http_client,
        )
    
    """ wait for client to be initialized first """
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

    async def get_daily_bars(self, symbol: str, output_size: OutputSize = "compact")-> list[DailyBar]:

        payload = await self._client.fetch_daily_raw(symbol=symbol, output_size=output_size)

        return parse_alpha_vantage_daily(payload)

    async def get_company_fundamentals(self, symbol: str) -> CompanyFundamentals:

        payload = await self._client.fetch_company_overview_raw(symbol=symbol)

        return parse_alpha_vantage_company_overview(payload)