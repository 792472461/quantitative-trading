from __future__ import annotations

from qt_trader.config import AppConfig
from qt_trader.data.akshare_data import AKShareDataFeed
from qt_trader.data.base import MarketDataFeed
from qt_trader.data.csv_data import CSVBarFeed


def create_data_feed(config: AppConfig) -> MarketDataFeed:
    provider = config.data.provider.lower()

    if provider == "csv":
        return CSVBarFeed(
            csv_path=config.data.csv_path,
            symbol=config.data.symbol,
            datetime_column=config.data.datetime_column,
        )

    if provider == "akshare":
        return AKShareDataFeed(
            symbol=config.data.symbol,
            period=config.data.period,
            start_date=config.data.start_date,
            end_date=config.data.end_date,
            adjust=config.data.adjust,
            output_csv_path=config.data.output_csv_path,
        )

    raise ValueError(f"Unsupported data provider: {config.data.provider}")
