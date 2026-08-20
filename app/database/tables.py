from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Identity,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

class DailyBarTable(Base):
    __tablename__ = "daily_bars"

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "trading_date",
            "source",
            "adjustment",
            name="daily_bar_identity",
        ),
        CheckConstraint(
            "open > 0",
            name="open_positive",
        ),
        CheckConstraint(
            "high>0",
            name="high_positive",
        ),
        CheckConstraint(
            "low>0",
            name="low_positive",
        ),
        CheckConstraint(
            "volume >= 0",
            name="volume_non_negative",
        ),
        CheckConstraint(
            "high >= open AND high >= close AND high >= low",
            name="high_price_range",
        ),
        CheckConstraint(
            "low <= open AND low <= close AND low <= high",
            name="low_price_range",
        ),
        CheckConstraint(
            "adjustment IN "
            "('raw', 'split_adjusted', 'total_return')",
            name="adjustment_valid",
        ),
        Index(
            "ix_daily_bars_symbol_trading_date",
            "symbol",
            "trading_date",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # python type: str; postgresql type: symbol VARCHAR(15) NOT NULL
    symbol: Mapped[str] = mapped_column(String(15), nullable=False)
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)

    open: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)

    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    adjustment: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)

    # Example:
    # received_at：10:00:00，data is returned from provider
    # created_at：10:00:03，data is inserted into database
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

class FundamentalSnapshotTable(Base):
    """ Everyday's fundamental data snapshot """

    __tablename__ = "fundamental_snapshots"

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "snapshot_date",
            "source",
            name="fundamental_snapshot_identity",
        ),
        Index(
            "ix_fundamental_snapshots_symbol_snapshot_date",
            "symbol",
            "snapshot_date",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(15), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    latest_quarter: Mapped[date | None] = mapped_column(Date, nullable=True)

    pe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    price_to_book_ratio: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    ebitda: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)

    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

class AnomalyEventTable(Base):
    """ Anomaly event table generated from pre-determined rules """

    __tablename__ = "anomaly_events"

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "trading_date",
            "event_type",
            name="anomaly_event_identity",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="severity_valid",
        ),
        Index(
            "ix_anomaly_events_symbol_trading_date",
            "symbol",
            "trading_date",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    symbol: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
    )
    trading_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    # Evidence fields change as Anomaly types are different. JSONB can store non-structured data.
    evidence: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )