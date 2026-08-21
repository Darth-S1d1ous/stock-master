from datetime import date

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_sources.fundamental_models import CompanyFundamentals
from app.data_sources.models import DailyBar, PriceAdjustment
from app.database.tables import (
    DailyBarTable,
    FundamentalSnapshotTable,
)

class StockDataRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_daily_bars(self, bars: list[DailyBar]) -> int:
        """ 
        save daily bars to database.

        existing daily bars will be updated
        return the numebr of rows affected
        """
        if not bars:
            return 0

        values = [
            {
                "symbol": bar.symbol,
                "trading_date": bar.trading_date,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "currency": bar.currency,
                "adjustment": bar.adjustment.value,
                "source": bar.source,
                "received_at": bar.received_at,
            }
            for bar in bars
        ]

        statement = insert(DailyBarTable).values(values)

        statement = statement.on_conflict_do_update(
            index_elements=[
                DailyBarTable.symbol,
                DailyBarTable.trading_date,
                DailyBarTable.source,
                DailyBarTable.adjustment,
            ],
            set_={
                "open": statement.excluded.open,
                "high": statement.excluded.high,
                "low": statement.excluded.low,
                "close": statement.excluded.close,
                "volume": statement.excluded.volume,
                "currency": statement.excluded.currency,
                "received_at": statement.excluded.received_at,
            }
        )

        await self._session.execute(statement)
        return len(bars)

    async def save_company_fundamentals(self, fundamentals: CompanyFundamentals, snapshot_date: date | None = None) -> None:
        effective_snapshot_date = (snapshot_date if snapshot_date is not None else fundamentals.received_at.date())

        statement = insert(FundamentalSnapshotTable).values(
            symbol=fundamentals.symbol,
            snapshot_date=effective_snapshot_date,
            latest_quarter=fundamentals.latest_quarter,
            pe_ratio=fundamentals.pe_ratio,
            price_to_book_ratio=fundamentals.price_to_book_ratio,
            ebitda=fundamentals.ebitda,
            currency=fundamentals.currency,
            source=fundamentals.source,
            received_at=fundamentals.received_at,
        )

        statement = statement.on_conflict_do_update(
            index_elements=[
                FundamentalSnapshotTable.symbol,
                FundamentalSnapshotTable.snapshot_date,
                FundamentalSnapshotTable.source,
            ],
            set_={
                "latest_quarter": statement.excluded.latest_quarter,
                "pe_ratio": statement.excluded.pe_ratio,
                "price_to_book_ratio": (
                    statement.excluded.price_to_book_ratio
                ),
                "ebitda": statement.excluded.ebitda,
                "currency": statement.excluded.currency,
                "received_at": statement.excluded.received_at,
            },
        )

        await self._session.execute(statement)

    async def get_recent_daily_bars(self, symbol: str, limit: int = 100) -> list[DailyBar]:
        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError("Symbol cannot be empty")
        if not 1 <= limit <= 1000:
            raise ValueError("Limit must be between 1 and 1000")

        statement: Select[tuple[DailyBarTable]] = (
            select(DailyBarTable)
            .where(DailyBarTable.symbol == normalized_symbol)
            .order_by(DailyBarTable.trading_date.desc())
            .limit(limit)
        )

        result = await self._session.execute(statement)
        rows = list(result.scalars())

        rows.reverse()

        return [
            DailyBar(
                observation_id=row.observation_id,
                symbol=row.symbol,
                trading_date=row.trading_date,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
                currency=row.currency,
                adjustment=PriceAdjustment(row.adjustment),
                source=row.source,
                received_at=row.received_at,
            )
            for row in rows
        ]

    async def get_latest_company_fundamentals(self, symbol: str) -> CompanyFundamentals | None:
        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError("Symbol cannot be empty")
        
        statement: Select[tuple[FundamentalSnapshotTable]] = (
            select(FundamentalSnapshotTable)
            .where(FundamentalSnapshotTable.symbol == normalized_symbol)
            .order_by(FundamentalSnapshotTable.snapshot_date.desc(), FundamentalSnapshotTable.received_at.desc(),)
            .limit(1)
        )

        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()

        if row is None:
            return None

        return CompanyFundamentals(
            observation_id=row.observation_id,
            symbol=row.symbol,
            latest_quarter=row.latest_quarter,
            pe_ratio=row.pe_ratio,
            price_to_book_ratio=row.price_to_book_ratio,
            ebitda=row.ebitda,
            currency=row.currency,
            source=row.source,
            received_at=row.received_at,
        )