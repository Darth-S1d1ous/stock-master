import asyncio
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from types import TracebackType
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from app.data_sources.base import OutputSize
from app.data_sources.fundamental_models import CompanyFundamentals
from app.data_sources.models import DailyBar, PriceAdjustment
from app.data_sources.settings import DataSourceSettings, get_settings


_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")
_ALLOWED_API_HOSTS = frozenset({"finnhub.io"})


class FinnhubError(Exception):
    """Finnhub 数据源异常基类。"""


class FinnhubRateLimitError(FinnhubError):
    """Finnhub 调用频率受限。"""


class FinnhubDataSource:
    """Finnhub 日线与基础估值数据源。"""

    def __init__(
        self,
        settings: DataSourceSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._validate_base_url(self._settings.finnhub_base_url)
        self._provided_http_client = http_client
        self._owned_http_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "FinnhubDataSource":
        if not self._settings.finnhub_api_key:
            raise ValueError("缺少 FINNHUB_API_KEY")
        if self._provided_http_client is None:
            self._owned_http_client = httpx.AsyncClient(
                base_url=self._settings.finnhub_base_url,
                timeout=httpx.Timeout(self._settings.finnhub_timeout_seconds),
                follow_redirects=False,
                headers={
                    "X-Finnhub-Token": self._settings.finnhub_api_key,
                },
            )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._owned_http_client is not None:
            await self._owned_http_client.aclose()
            self._owned_http_client = None

    async def get_daily_bars(
        self,
        symbol: str,
        output_size: OutputSize = "compact",
    ) -> list[DailyBar]:
        normalized_symbol = self._normalize_symbol(symbol)
        now = datetime.now(UTC)
        start = now - (
            timedelta(days=180)
            if output_size == "compact"
            else timedelta(days=365 * 20)
        )
        payload = await self._get_json(
            "/api/v1/stock/candle",
            params={
                "symbol": normalized_symbol,
                "resolution": "D",
                "from": str(int(start.timestamp())),
                "to": str(int(now.timestamp())),
            },
        )
        return self._parse_daily_bars(normalized_symbol, payload, output_size)

    async def get_company_fundamentals(
        self,
        symbol: str,
    ) -> CompanyFundamentals:
        normalized_symbol = self._normalize_symbol(symbol)
        payload = await self._get_json(
            "/api/v1/stock/metric",
            params={"symbol": normalized_symbol, "metric": "all"},
        )
        return self._parse_fundamentals(normalized_symbol, payload)

    async def _get_json(
        self,
        path: str,
        params: dict[str, str],
    ) -> Mapping[str, object]:
        client = self._get_http_client()
        max_attempts = self._settings.finnhub_max_retries + 1

        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.get(path, params=params)
            except (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.RemoteProtocolError,
            ) as exc:
                if attempt == max_attempts:
                    raise FinnhubError("Finnhub 网络请求失败") from exc
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
                continue

            if response.status_code == 429:
                raise FinnhubRateLimitError("Finnhub API 调用频率受限")
            if 500 <= response.status_code < 600 and attempt < max_attempts:
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
                continue
            try:
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPStatusError, ValueError) as exc:
                raise FinnhubError(
                    f"Finnhub 返回无效响应，HTTP {response.status_code}"
                ) from exc

            if not isinstance(payload, Mapping):
                raise FinnhubError("Finnhub JSON 顶层必须是对象")
            error = payload.get("error")
            if isinstance(error, str) and error:
                raise FinnhubError(f"Finnhub 拒绝请求：{error}")
            return payload

        raise FinnhubError("Finnhub 请求未获得响应")

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._provided_http_client is not None:
            return self._provided_http_client
        if self._owned_http_client is None:
            raise RuntimeError("请使用 async with 管理 FinnhubDataSource")
        return self._owned_http_client

    @staticmethod
    def _parse_daily_bars(
        symbol: str,
        payload: Mapping[str, object],
        output_size: OutputSize,
    ) -> list[DailyBar]:
        status = payload.get("s")
        if status == "no_data":
            raise FinnhubError(f"Finnhub 没有返回日线数据：{symbol}")
        if status != "ok":
            raise FinnhubError(f"Finnhub 日线状态异常：{status!r}")

        opens = FinnhubDataSource._require_sequence(payload, "o")
        highs = FinnhubDataSource._require_sequence(payload, "h")
        lows = FinnhubDataSource._require_sequence(payload, "l")
        closes = FinnhubDataSource._require_sequence(payload, "c")
        volumes = FinnhubDataSource._require_sequence(payload, "v")
        timestamps = FinnhubDataSource._require_sequence(payload, "t")
        arrays = (opens, highs, lows, closes, volumes, timestamps)
        lengths = {len(values) for values in arrays}
        if len(lengths) != 1 or lengths == {0}:
            raise FinnhubError("Finnhub 日线数组长度不一致或为空")

        received_at = datetime.now(UTC)
        bars: list[DailyBar] = []
        try:
            for index in range(len(opens)):
                bars.append(
                    DailyBar(
                        symbol=symbol,
                        trading_date=datetime.fromtimestamp(
                            int(str(timestamps[index])), tz=UTC
                        ).date(),
                        open=FinnhubDataSource._to_decimal(opens[index]),
                        high=FinnhubDataSource._to_decimal(highs[index]),
                        low=FinnhubDataSource._to_decimal(lows[index]),
                        close=FinnhubDataSource._to_decimal(closes[index]),
                        volume=FinnhubDataSource._to_volume(volumes[index]),
                        currency="USD",
                        adjustment=PriceAdjustment.RAW,
                        source="finnhub",
                        received_at=received_at,
                    )
                )
        except (InvalidOperation, TypeError, ValueError, ValidationError) as exc:
            raise FinnhubError(f"Finnhub 日线解析失败：{symbol}") from exc

        bars.sort(key=lambda bar: bar.trading_date)
        return bars[-100:] if output_size == "compact" else bars

    @staticmethod
    def _parse_fundamentals(
        symbol: str,
        payload: Mapping[str, object],
    ) -> CompanyFundamentals:
        metric = payload.get("metric")
        if not isinstance(metric, Mapping):
            raise FinnhubError("Finnhub 基本面响应缺少 metric")

        try:
            return CompanyFundamentals(
                symbol=symbol,
                latest_quarter=FinnhubDataSource._latest_period(
                    payload.get("series")
                ),
                pe_ratio=FinnhubDataSource._first_decimal(
                    metric, "peTTM", "peBasicExclExtraTTM"
                ),
                price_to_book_ratio=FinnhubDataSource._first_decimal(
                    metric, "pbQuarterly", "pbAnnual"
                ),
                ebitda=FinnhubDataSource._first_decimal(
                    metric, "ebitda", "ebitdaTTM", "ebitdTTM"
                ),
                currency="USD",
                source="finnhub",
                received_at=datetime.now(UTC),
            )
        except (ValueError, ValidationError) as exc:
            raise FinnhubError(f"Finnhub 基本面解析失败：{symbol}") from exc

    @staticmethod
    def _latest_period(value: object) -> date | None:
        if not isinstance(value, Mapping):
            return None
        candidates: list[date] = []
        for group in value.values():
            if not isinstance(group, Mapping):
                continue
            for records in group.values():
                if not isinstance(records, Sequence):
                    continue
                for record in records:
                    if not isinstance(record, Mapping):
                        continue
                    period = record.get("period")
                    if isinstance(period, str):
                        try:
                            candidates.append(date.fromisoformat(period[:10]))
                        except ValueError:
                            continue
        return max(candidates) if candidates else None

    @staticmethod
    def _first_decimal(
        payload: Mapping[str, object],
        *keys: str,
    ) -> Decimal | None:
        for key in keys:
            value = payload.get(key)
            if value is None or value == "":
                continue
            parsed = FinnhubDataSource._to_decimal(value)
            if parsed.is_finite():
                return parsed
        return None

    @staticmethod
    def _require_sequence(
        payload: Mapping[str, object],
        key: str,
    ) -> Sequence[object]:
        value = payload.get(key)
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise FinnhubError(f"Finnhub 日线字段 {key!r} 不是数组")
        return value

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"无效数值：{value!r}") from exc
        if not parsed.is_finite():
            raise ValueError(f"数值必须有限：{value!r}")
        return parsed

    @staticmethod
    def _to_volume(value: object) -> int:
        parsed = FinnhubDataSource._to_decimal(value)
        if parsed < 0 or parsed != parsed.to_integral_value():
            raise ValueError(f"无效成交量：{value!r}")
        return int(parsed)

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("股票代码格式无效")
        return normalized

    @staticmethod
    def _validate_base_url(base_url: str) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_API_HOSTS:
            raise ValueError("Finnhub API 地址必须是 https://finnhub.io")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Finnhub API 地址不能包含用户名或密码")
