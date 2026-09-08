import unittest

from app.data_sources.alpha_vantage_adapter import AlphaVantageAdapter
from app.data_sources.base import StockDataSource
from app.data_sources.finnhub_adapter import FinnhubAdapter
from app.data_sources.provider_factory import (
    SUPPORTED_PROVIDERS,
    create_data_source,
    register_adapter,
)
from app.data_sources.yahoo_finance_adapter import YahooFinanceAdapter


class AdapterRegistryTests(unittest.TestCase):
    def test_builtin_adapters_are_registered(self) -> None:
        self.assertEqual(
            SUPPORTED_PROVIDERS,
            ("alpha_vantage", "finnhub", "yahoo_finance"),
        )
        self.assertTrue(issubclass(AlphaVantageAdapter, StockDataSource))
        self.assertTrue(issubclass(FinnhubAdapter, StockDataSource))
        self.assertTrue(issubclass(YahooFinanceAdapter, StockDataSource))

    def test_create_yahoo_finance_adapter(self) -> None:
        adapter = create_data_source("yahoo_finance")
        self.assertIsInstance(adapter, YahooFinanceAdapter)
        self.assertIsInstance(adapter, StockDataSource)

    def test_rejects_unknown_provider(self) -> None:
        with self.assertRaises(ValueError) as context:
            create_data_source("unknown_vendor")
        self.assertIn("Unsupported provider", str(context.exception))

    def test_register_adapter_extends_factory_without_changing_callers(self) -> None:
        class StubAdapter(StockDataSource):
            async def get_daily_bars(self, symbol: str, output_size: str = "compact"):
                raise NotImplementedError

            async def get_company_fundamentals(self, symbol: str):
                raise NotImplementedError

        register_adapter("stub_vendor", StubAdapter)
        try:
            adapter = create_data_source("stub_vendor")
            self.assertIsInstance(adapter, StubAdapter)
        finally:
            from app.data_sources import provider_factory

            provider_factory._ADAPTER_REGISTRY.pop("stub_vendor", None)
