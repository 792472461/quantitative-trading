from __future__ import annotations

from pathlib import Path

import pandas as pd

from qt_trader.data.base import MarketDataFeed
from qt_trader.models import Bar


class CSVBarFeed(MarketDataFeed):
    def __init__(
        self,
        csv_path: str | Path | None,
        symbol: str,
        datetime_column: str = "datetime",
        symbol_column: str = "symbol",
        csv_paths: dict[str, str | Path] | None = None,
    ) -> None:
        self.csv_path = Path(csv_path) if csv_path else None
        self.csv_paths = {item_symbol: Path(item_path) for item_symbol, item_path in (csv_paths or {}).items()}
        self.symbol = symbol
        self.datetime_column = datetime_column
        self.symbol_column = symbol_column

    def load(self) -> list[Bar]:
        if self.csv_paths:
            frames = []
            for item_symbol, item_path in self.csv_paths.items():
                frame = pd.read_csv(item_path)
                frame[self.symbol_column] = item_symbol
                frames.append(frame)
            frame = pd.concat(frames, ignore_index=True)
        elif self.csv_path is not None:
            frame = pd.read_csv(self.csv_path)
        else:
            raise ValueError("Either csv_path or csv_paths must be provided")

        frame[self.datetime_column] = pd.to_datetime(frame[self.datetime_column])
        if self.symbol_column not in frame.columns:
            frame[self.symbol_column] = self.symbol
        frame = frame.sort_values([self.datetime_column, self.symbol_column])

        return [
            Bar(
                symbol=str(row[self.symbol_column]),
                timestamp=row[self.datetime_column].to_pydatetime(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            for _, row in frame.iterrows()
        ]
