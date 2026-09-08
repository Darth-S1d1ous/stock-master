from collections.abc import Callable

from app.data_sources.alpha_vantage_adapter import AlphaVantageAdapter
from app.data_sources.base import StockDataSource
from app.data_sources.finnhub_adapter import FinnhubAdapter
from app.data_sources.yahoo_finance_adapter import YahooFinanceAdapter

# a Callable with no arguments that returns a StockDataSource
ProviderFactory = Callable[[], StockDataSource]

_ADAPTER_REGISTRY: dict[str, ProviderFactory] = {}


def register_adapter(name: str, factory: ProviderFactory) -> None:
    """Register a ``StockDataSource`` adapter under a provider key.

    New providers extend this registry; ``create_data_source`` does not change.
    """

    key = name.strip().lower()
    if not key:
        raise ValueError("Adapter name is required")
    if not callable(factory):
        raise TypeError("Adapter factory must be callable")
    _ADAPTER_REGISTRY[key] = factory


def supported_providers() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTER_REGISTRY))

# Simple Factory
def create_data_source(provider: str) -> StockDataSource:
    """Create a market-data adapter from the registered provider allowlist."""

    normalized = provider.strip().lower()
    factory = _ADAPTER_REGISTRY.get(normalized)
    if factory is None:
        supported = ", ".join(supported_providers())
        raise ValueError(f"Unsupported provider. Expected one of: {supported}")
    return factory()


register_adapter("alpha_vantage", AlphaVantageAdapter)
register_adapter("finnhub", FinnhubAdapter)
register_adapter("yahoo_finance", YahooFinanceAdapter)

SUPPORTED_PROVIDERS = supported_providers()
