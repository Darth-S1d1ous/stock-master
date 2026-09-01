from collections.abc import Callable

from app.data_sources.alpha_vantage_data_source import AlphaVantageDataSource
from app.data_sources.base import StockDataSource
from app.data_sources.finnhub_data_source import FinnhubDataSource
from app.data_sources.yahoo_finance_data_source import YahooFinanceDataSource

ProviderFactory = Callable[[], StockDataSource]

_PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "alpha_vantage": AlphaVantageDataSource,
    "finnhub": FinnhubDataSource,
    "yahoo_finance": YahooFinanceDataSource,
}

SUPPORTED_PROVIDERS = tuple(sorted(_PROVIDER_FACTORIES))


def create_data_source(provider: str) -> StockDataSource:
    """Create a market-data source from the fixed provider allowlist."""

    normalized = provider.strip().lower()
    factory = _PROVIDER_FACTORIES.get(normalized)
    if factory is None:
        supported = ", ".join(SUPPORTED_PROVIDERS)
        raise ValueError(f"Unsupported provider. Expected one of: {supported}")
    return factory()
