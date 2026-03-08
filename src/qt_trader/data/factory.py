from __future__ import annotations

from qt_trader.config import AppConfig
from qt_trader.data.akshare_data import AKShareDataFeed
from qt_trader.data.base import MarketDataFeed
from qt_trader.data.csv_data import CSVBarFeed
from qt_trader.data.qmt_live import QMTLiveDataFeed


def create_data_feed(config: AppConfig) -> MarketDataFeed:
    provider = config.data.provider.lower()
    symbols = config.data.symbols or [config.data.symbol]
    primary_symbol = symbols[0]

    if provider == "csv":
        if config.data.csv_path is None:
            raise ValueError("CSV data provider requires data.csv_path")
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

    if provider == "qmt_live":
        return QMTLiveDataFeed(
            symbols=symbols,
            period=config.data.period,
            bar_window=config.data.bar_window,
            xtquant_module=config.data.xtquant_module,
            subscribe_live_quotes=config.data.subscribe_live_quotes,
        )

    raise ValueError(f"Unsupported data provider: {config.data.provider}")
