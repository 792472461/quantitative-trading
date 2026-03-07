from __future__ import annotations

from qt_trader.config import AppConfig
from qt_trader.data.akshare_data import AKShareDataFeed
from qt_trader.data.base import MarketDataFeed
from qt_trader.data.csv_data import CSVBarFeed


def create_data_feed(config: AppConfig) -> MarketDataFeed:
    provider = config.data.provider.lower()
    symbols = config.data.symbols or [config.data.symbol]
    primary_symbol = symbols[0]

    if provider == "csv":
        return CSVBarFeed(
            csv_path=config.data.csv_path,
            csv_paths=config.data.csv_paths,
            symbol=primary_symbol,
            datetime_column=config.data.datetime_column,
            symbol_column=config.data.symbol_column,
        )

    if provider == "akshare":
        return AKShareDataFeed(
            symbol=primary_symbol,
            symbols=symbols,
            period=config.data.period,
            start_date=config.data.start_date,
            end_date=config.data.end_date,
            adjust=config.data.adjust,
            output_csv_path=config.data.output_csv_path,
        )

    raise ValueError(f"Unsupported data provider: {config.data.provider}")
