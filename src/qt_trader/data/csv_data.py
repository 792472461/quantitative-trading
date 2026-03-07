from __future__ import annotations

from pathlib import Path

import pandas as pd

from qt_trader.models import Bar


class CSVBarFeed:
    def __init__(self, csv_path: str | Path, symbol: str, datetime_column: str = "datetime") -> None:
        self.csv_path = Path(csv_path)
        self.symbol = symbol
        self.datetime_column = datetime_column

    def load(self) -> list[Bar]:
        frame = pd.read_csv(self.csv_path)
        frame[self.datetime_column] = pd.to_datetime(frame[self.datetime_column])
        frame = frame.sort_values(self.datetime_column)

        return [
            Bar(
                symbol=self.symbol,
                timestamp=row[self.datetime_column].to_pydatetime(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            for _, row in frame.iterrows()
        ]
