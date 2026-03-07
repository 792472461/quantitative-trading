from __future__ import annotations

from pathlib import Path

import pandas as pd

from qt_trader.data.base import MarketDataFeed
from qt_trader.models import Bar


class AKShareDataFeed(MarketDataFeed):
    def __init__(
        self,
        symbol: str,
        symbols: list[str] | None = None,
        period: str = "daily",
        start_date: str | None = None,
        end_date: str | None = None,
        adjust: str = "",
        output_csv_path: str | Path | None = None,
    ) -> None:
        self.symbol = symbol
        self.symbols = symbols or [symbol]
        self.period = period
        self.start_date = start_date
        self.end_date = end_date
        self.adjust = adjust
        self.output_csv_path = Path(output_csv_path) if output_csv_path else None

    def _fetch_frame(self, symbol: str) -> pd.DataFrame:
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("AKShare is not installed. Run `pip install -e .[dev]` again.") from exc

        frame = ak.stock_zh_a_hist(
            symbol=symbol,
            period=self.period,
            start_date=self.start_date or "19700101",
            end_date=self.end_date or "22220101",
            adjust=self.adjust,
        )
        if frame.empty:
            raise ValueError(f"No market data returned for symbol={symbol}")
        return frame

    def load(self) -> list[Bar]:
        try:
            frames = []
            for symbol in self.symbols:
                frame = self._fetch_frame(symbol)
                normalized_frame = pd.DataFrame(
                    {
                        "symbol": symbol,
                        "datetime": pd.to_datetime(frame["日期"]),
                        "open": frame["开盘"].astype(float),
                        "high": frame["最高"].astype(float),
                        "low": frame["最低"].astype(float),
                        "close": frame["收盘"].astype(float),
                        "volume": frame["成交量"].astype(float),
                    }
                )
                frames.append(normalized_frame)
            normalized = pd.concat(frames, ignore_index=True).sort_values(["datetime", "symbol"])
        except Exception:
            if self.output_csv_path is None or not self.output_csv_path.exists():
                raise
            normalized = pd.read_csv(self.output_csv_path)
            normalized["datetime"] = pd.to_datetime(normalized["datetime"])
            if "symbol" not in normalized.columns:
                normalized["symbol"] = self.symbol

        if self.output_csv_path is not None:
            self.output_csv_path.parent.mkdir(parents=True, exist_ok=True)
            normalized.to_csv(self.output_csv_path, index=False)

        return [
            Bar(
                symbol=str(row["symbol"]),
                timestamp=row["datetime"].to_pydatetime(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            for _, row in normalized.iterrows()
        ]
