from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.data_sources.base import OutputSize, StockDataSource
from app.database.repositories import StockDataRepository

@dataclass(frozen=True, slots=True)
class IngestionResult:
    symbol: str
    daily_bars_processed: int
    earliest_trading_date: date
    latest_trading_date: date
    fundamental_snapshot_date: date

class StockIngestionService:
    """ Obtaining data from sources and atomically save them to database """

    def __init__(self, session: AsyncSession, data_source: StockDataSource) -> None:
        self._session = session
        self._data_source = data_source
        self._repository = StockDataRepository(session)

    async def refresh_symbol(
        self,
        symbol: str,
        output_size: OutputSize = "compact",
    ) -> IngestionResult:
        """ web request before database operation """

        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError("Symbol cannot be empty")

        bars = await self._data_source.get_daily_bars(
            symbol=normalized_symbol,
            output_size=output_size,
        )
        if not bars:
            raise ValueError("Data source returned no daily bars")

        fundamentals = await self._data_source.get_company_fundamentals(
            symbol=normalized_symbol,
        )

        self._validate_symbols(
            requested_symbol=normalized_symbol,
            bars_symbol=bars[0].symbol,
            fundamentals_symbol=fundamentals.symbol,
        )

        snapshot_date = fundamentals.received_at.date()

        try:
            processed_count = (await self._repository.save_daily_bars(bars))
            await self._repository.save_company_fundamentals(
                fundamentals=fundamentals,
                snapshot_date=snapshot_date,
            )

            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return IngestionResult(
            symbol=normalized_symbol,
            daily_bars_processed=processed_count,
            earliest_trading_date=bars[0].trading_date,
            latest_trading_date=bars[-1].trading_date,
            fundamental_snapshot_date=snapshot_date,
        )
    
    @staticmethod
    def _validate_symbols(requested_symbol: str, bars_symbol: str, fundamentals_symbol: str) -> None:
        """ Make sure the symbol is the same as the requested symbol """
        if bars_symbol != requested_symbol:
            raise ValueError(
                "日线数据的股票代码与请求代码不一致："
                f"请求 {requested_symbol}，返回 {bars_symbol}"
            )

        if fundamentals_symbol != requested_symbol:
            raise ValueError(
                "基本面数据的股票代码与请求代码不一致："
                f"请求 {requested_symbol}，"
                f"返回 {fundamentals_symbol}"
            )