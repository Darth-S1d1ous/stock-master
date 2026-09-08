```
Application code
   ↓
StockDataSource (Target)
   ↓
Adapter registry (`create_data_source`)
   ├── AlphaVantageAdapter  → AlphaVantageClient (Adaptee)
   │      ├── Daily-bar parser        → list[DailyBar]
   │      └── Fundamentals parser     → CompanyFundamentals
   ├── FinnhubAdapter       → FinnhubClient (Adaptee)
   │      └── Finnhub parsers
   └── YahooFinanceAdapter  → yfinance (Adaptee)
```

Each adapter translates a third-party API into the shared `StockDataSource`
contract. Register a new adapter with `register_adapter` instead of changing
callers.
