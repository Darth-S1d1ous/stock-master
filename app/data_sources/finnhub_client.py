import asyncio
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self
from urllib.parse import urlsplit

import httpx

from app.data_sources.base import OutputSize
from app.data_sources.settings import DataSourceSettings, get_settings

_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")
_ALLOWED_API_HOSTS = frozenset({"finnhub.io"})


class FinnhubError(Exception):
    """Base exception for Finnhub data source errors."""


class FinnhubRateLimitError(FinnhubError):
    """Finnhub rate limit reached."""


class FinnhubClient:
    """HTTP adaptee for the Finnhub REST API."""

    def __init__(
        self,
        settings: DataSourceSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._validate_base_url(self._settings.finnhub_base_url)
        self._provided_http_client = http_client
        self._owned_http_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        if not self._settings.finnhub_api_key.get_secret_value():
            raise ValueError("FINNHUB_API_KEY is required")
        if self._provided_http_client is None:
            self._owned_http_client = httpx.AsyncClient(
                base_url=self._settings.finnhub_base_url,
                timeout=httpx.Timeout(self._settings.finnhub_timeout_seconds),
                follow_redirects=False,
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

    async def fetch_daily_raw(
        self,
        symbol: str,
        output_size: OutputSize = "compact",
    ) -> Mapping[str, object]:
        normalized_symbol = self.normalize_symbol(symbol)
        self.validate_output_size(output_size)
        now = datetime.now(UTC)
        start = now - (
            timedelta(days=180)
            if output_size == "compact"
            else timedelta(days=365 * 20)
        )
        return await self._get_json(
            "/api/v1/stock/candle",
            params={
                "symbol": normalized_symbol,
                "resolution": "D",
                "from": str(int(start.timestamp())),
                "to": str(int(now.timestamp())),
            },
        )

    async def fetch_metrics_raw(self, symbol: str) -> Mapping[str, object]:
        normalized_symbol = self.normalize_symbol(symbol)
        return await self._get_json(
            "/api/v1/stock/metric",
            params={"symbol": normalized_symbol, "metric": "all"},
        )

    async def _get_json(
        self,
        path: str,
        params: dict[str, str],
    ) -> Mapping[str, object]:
        client = self._get_http_client()
        max_attempts = self._settings.finnhub_max_retries + 1
        url = f"{self._settings.finnhub_base_url.rstrip('/')}{path}"
        headers = {
            "X-Finnhub-Token": self._settings.finnhub_api_key.get_secret_value(),
        }

        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.get(
                    url,
                    params=params,
                    headers=headers,
                    follow_redirects=False,
                )
            except (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.RemoteProtocolError,
            ):
                if attempt == max_attempts:
                    raise FinnhubError("Finnhub network request failed") from None
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
                continue

            if response.status_code == 429:
                raise FinnhubRateLimitError("Finnhub API rate limit reached")
            if 500 <= response.status_code < 600 and attempt < max_attempts:
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
                continue
            try:
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPStatusError, ValueError):
                raise FinnhubError(
                    f"Finnhub returned an invalid response with HTTP status {response.status_code}"
                ) from None

            if not isinstance(payload, Mapping):
                raise FinnhubError("Finnhub JSON root must be an object")
            error = payload.get("error")
            if isinstance(error, str) and error:
                raise FinnhubError("Finnhub rejected the request")
            return payload

        raise FinnhubError("Finnhub request returned no response")

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._provided_http_client is not None:
            return self._provided_http_client
        if self._owned_http_client is None:
            raise RuntimeError("Use async with to manage FinnhubClient")
        return self._owned_http_client

    @staticmethod
    def validate_output_size(output_size: str) -> None:
        if output_size not in ("compact", "full"):
            raise ValueError("output_size must be 'compact' or 'full'")

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("Invalid stock symbol format")
        return normalized

    @staticmethod
    def _validate_base_url(base_url: str) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_API_HOSTS:
            raise ValueError("Finnhub API URL must be https://finnhub.io")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Finnhub API URL must not contain a username or password")
