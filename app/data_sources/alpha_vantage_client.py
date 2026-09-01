import asyncio
import re
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.data_sources.settings import DataSourceSettings, get_settings

_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")
_ALLOWED_API_HOSTS = frozenset({"www.alphavantage.co"})

class AlphaVantageError(Exception):
    """ Alpha Vantage exception base"""

class AlphaVantageRequestError(AlphaVantageError):
    """ network error or server not available """

class AlphaVantageRateLimitError(AlphaVantageError):
    """ API rate limit exceeded """

class AlphaVantageResponseError(AlphaVantageError):
    """ API response error """

class AlphaVantageClient:

    def __init__ (
        self,
        settings: DataSourceSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    )-> None:

        self._settings = settings or get_settings()
        if not self._settings.alpha_vantage_api_key.get_secret_value():
            raise ValueError("ALPHA_VANTAGE_API_KEY is required")
        self._validate_base_url(self._settings.alpha_vantage_base_url)

        self._provided_http_client = http_client
        self._owned_http_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AlphaVantageClient":
        """ if no http client is provided, create one """

        if self._provided_http_client is None:
            self._owned_http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.alpha_vantage_timeout_seconds),
                follow_redirects=False,
            )

        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        if self._owned_http_client is not None:
            await self._owned_http_client.aclose()
            self._owned_http_client = None

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._provided_http_client is not None:
            return self._provided_http_client

        if self._owned_http_client is None:
            raise RuntimeError(
                "Please use 'async with' to create a client"
            )

        return self._owned_http_client

    async def fetch_daily_raw(
        self, 
        symbol: str,
        output_size: str = "compact"
    ) -> dict[str, Any]:

        normalized_symbol = self._normalize_symbol(symbol)

        if output_size not in ("compact", "full"):
            raise ValueError(f"Invalid output size: {output_size}. Can only be 'compact' or 'full'")

        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": normalized_symbol,
            "outputsize": output_size,
            "datatype": "json",
            "apikey": self._settings.alpha_vantage_api_key.get_secret_value(),
        }

        response = await self._get_with_retry(params)

        try:
            payload = response.json()
        except ValueError as exc:
            raise AlphaVantageResponseError("Invalid JSON response") from exc

        if not isinstance(payload, dict):
            raise AlphaVantageResponseError("The top level of the response is not a dict")

        self._raise_for_api_error(payload)

        return payload

    """ obtain company Fundamental and Financial data from Alpha Vantage """
    async def fetch_company_overview_raw(self, symbol: str) -> dict[str, Any]:
        normalized_symbol = self._normalize_symbol(symbol)

        params = {
            "function": "OVERVIEW",
            "symbol": normalized_symbol,
            "apikey": self._settings.alpha_vantage_api_key.get_secret_value(),
        }

        response = await self._get_with_retry(params)

        try:
            payload = response.json()
        except ValueError as exc:
            raise AlphaVantageResponseError("Alpha Vantage company overview returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise AlphaVantageResponseError("Alpha Vantage company overview returned invalid JSON")

        self._raise_for_api_error(payload)

        if not payload:
            raise AlphaVantageResponseError(f"No company overview data found for {normalized_symbol}")

        returned_symbol = payload.get("Symbol")

        if not isinstance(returned_symbol, str):
            raise AlphaVantageResponseError("Company overview response is missing Symbol")

        if returned_symbol.strip().upper() != normalized_symbol:
            raise AlphaVantageResponseError("Company overview returned an unexpected symbol")

        return payload

    async def _get_with_retry(self, params: dict[str, Any]) -> httpx.Response:
        client = self._get_http_client()
        max_attempts = self._settings.alpha_vantage_max_retries + 1

        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.get(
                self._settings.alpha_vantage_base_url,
                params=params,
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
                    raise AlphaVantageRequestError(
                        f"request failed after {max_attempts} attempts"
                    ) from None

                await asyncio.sleep(self._retry_delay(attempt))
                continue

            if response.status_code == 429:
                raise AlphaVantageRateLimitError("API rate limit exceeded. Please retry later")

            if 500 <= response.status_code < 600:
                if attempt == max_attempts:
                    raise AlphaVantageRequestError(f"Alpha Vantage server error: {response.status_code}")

                await asyncio.sleep(self._retry_delay(attempt))
                continue
            
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                raise AlphaVantageRequestError(
                    f"Alpha Vantage request failed with HTTP {response.status_code}"
                ) from None

            return response

        raise AlphaVantageRequestError("Alpha Vantage request exhausted retries")

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()

        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError(f"Invalid symbol: {symbol}. Must be 1-15 characters long and contain only letters, numbers, dots, and hyphens, and start with a letter.")

        return normalized

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        return min(2 ** (attempt - 1), 8)

    @staticmethod
    def _raise_for_api_error(payload: dict[str, Any]) -> None:
        error_message = payload.get("Error Message")
        if isinstance(error_message, str):
            raise AlphaVantageResponseError("Alpha Vantage rejected request")

        note = payload.get("Note")
        if isinstance(note, str):
            raise AlphaVantageRateLimitError("Alpha Vantage rate limit exceeded")

        information = payload.get("Information")
        if isinstance(information, str):
            raise AlphaVantageResponseError("Alpha Vantage API error")

    @staticmethod
    def _validate_base_url(base_url: str) -> None:
        parsed = urlsplit(base_url)

        if parsed.scheme != "https":
            raise ValueError(f"Invalid base URL: {base_url}. Scheme must be 'https'")

        if parsed.hostname not in _ALLOWED_API_HOSTS:
            raise ValueError(f"Invalid base URL: {base_url}. Hostname must be one of {_ALLOWED_API_HOSTS}")

        if parsed.username is not None or parsed.password is not None:
            raise ValueError(f"Invalid base URL: {base_url}. Username and password are not allowed")