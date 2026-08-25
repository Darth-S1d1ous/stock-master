import asyncio
import math
import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from types import TracebackType

import yfinance as yf
from pydantic import ValidationError

from app.data_sources.base import OutputSize
from app.data_sources.fundamental_models import CompanyFundamentals
from app.data_sources.models import DailyBar, PriceAdjustment


_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")


class YahooFinanceError(Exception):
    """Yahoo Finance 数据源异常。"""


class YahooFinanceDataSource:
    """通过 yfinance 获取 Yahoo Finance 日线与基本面数据。"""

    async def __aenter__(self) -> "YahooFinanceDataSource":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def get_daily_bars(
        self,
        symbol: str,
        output_size: OutputSize = "compact",
    ) -> list[DailyBar]:
        normalized_symbol = self._normalize_symbol(symbol)
        self._validate_output_size(output_size)
        period = "6mo" if output_size == "compact" else "max"
        return await asyncio.to_thread(
            self._get_daily_bars_sync,
            normalized_symbol,
            period,
        )

    async def get_company_fundamentals(
        self,
        symbol: str,
    ) -> CompanyFundamentals:
        normalized_symbol = self._normalize_symbol(symbol)
        return await asyncio.to_thread(
            self._get_company_fundamentals_sync,
            normalized_symbol,
        )

    @staticmethod
    def _get_daily_bars_sync(
        symbol: str,
        period: str,
    ) -> list[DailyBar]:
        try:
            history = yf.Ticker(symbol).history(
                period=period,
                interval="1d",
                auto_adjust=False,
                actions=False,
                repair=True,
                raise_errors=True,
            )
        except Exception as exc:
            raise YahooFinanceError(
                f"Yahoo Finance 日线请求失败：{symbol}"
            ) from exc

        if history.empty:
            raise YahooFinanceError(
                f"Yahoo Finance 没有返回日线数据：{symbol}"
            )

        received_at = datetime.now(UTC)
        bars: list[DailyBar] = []

        for timestamp, row in history.iterrows():
            try:
                trading_date = date.fromisoformat(str(timestamp)[:10])
                open_price = YahooFinanceDataSource._to_decimal(row["Open"])
                high_price = YahooFinanceDataSource._to_decimal(row["High"])
                low_price = YahooFinanceDataSource._to_decimal(row["Low"])
                close_price = YahooFinanceDataSource._to_decimal(row["Close"])
                volume = YahooFinanceDataSource._to_int(row["Volume"])

                bars.append(
                    DailyBar(
                        symbol=symbol,
                        trading_date=trading_date,
                        open=open_price,
                        high=high_price,
                        low=low_price,
                        close=close_price,
                        volume=volume,
                        currency="USD",
                        adjustment=PriceAdjustment.RAW,
                        source="yahoo_finance",
                        received_at=received_at,
                    )
                )
            except (KeyError, ValueError, ValidationError) as exc:
                raise YahooFinanceError(
                    f"Yahoo Finance 日线解析失败：{symbol} {timestamp}"
                ) from exc

        bars.sort(key=lambda bar: bar.trading_date)
        return bars[-100:] if period == "6mo" else bars

    @staticmethod
    def _get_company_fundamentals_sync(
        symbol: str,
    ) -> CompanyFundamentals:
        try:
            info = yf.Ticker(symbol).get_info()
        except Exception as exc:
            raise YahooFinanceError(
                f"Yahoo Finance 基本面请求失败：{symbol}"
            ) from exc

        if not isinstance(info, dict) or not info:
            raise YahooFinanceError(
                f"Yahoo Finance 没有返回基本面数据：{symbol}"
            )

        returned_symbol = str(info.get("symbol", symbol)).strip().upper()
        if returned_symbol != symbol:
            raise YahooFinanceError(
                f"Yahoo Finance 返回了错误的股票代码：{returned_symbol}"
            )

        try:
            return CompanyFundamentals(
                symbol=symbol,
                latest_quarter=YahooFinanceDataSource._to_optional_date(
                    info.get("mostRecentQuarter")
                ),
                pe_ratio=YahooFinanceDataSource._to_optional_decimal(
                    info.get("trailingPE")
                ),
                price_to_book_ratio=(
                    YahooFinanceDataSource._to_optional_decimal(
                        info.get("priceToBook")
                    )
                ),
                ebitda=YahooFinanceDataSource._to_optional_decimal(
                    info.get("ebitda")
                ),
                currency=str(
                    info.get("financialCurrency")
                    or info.get("currency")
                    or "USD"
                ).upper(),
                source="yahoo_finance",
                received_at=datetime.now(UTC),
            )
        except (ValueError, ValidationError) as exc:
            raise YahooFinanceError(
                f"Yahoo Finance 基本面解析失败：{symbol}"
            ) from exc

    @staticmethod
    def _validate_output_size(output_size: str) -> None:
        if output_size not in ("compact", "full"):
            raise ValueError("output_size 必须是 'compact' 或 'full'")

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("股票代码格式无效")
        return normalized

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        parsed = YahooFinanceDataSource._to_optional_decimal(value)
        if parsed is None:
            raise ValueError("价格不能为空")
        return parsed

    @staticmethod
    def _to_optional_decimal(value: object) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, float) and not math.isfinite(value):
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"无效数值：{value!r}") from exc
        return parsed if parsed.is_finite() else None

    @staticmethod
    def _to_int(value: object) -> int:
        parsed = YahooFinanceDataSource._to_optional_decimal(value)
        if parsed is None or parsed < 0 or parsed != parsed.to_integral_value():
            raise ValueError(f"无效成交量：{value!r}")
        return int(parsed)

    @staticmethod
    def _to_optional_date(value: object) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=UTC).date()
        if isinstance(value, str) and value.strip():
            return date.fromisoformat(value.strip()[:10])
        return None