from __future__ import annotations

import importlib
from datetime import datetime
from typing import Any

import pandas as pd

from qt_trader.data.base import MarketDataFeed
from qt_trader.models import Bar


class QMTLiveDataFeed(MarketDataFeed):
    def __init__(
        self,
        symbols: list[str],
        period: str = "1m",
        bar_window: int = 240,
        xtquant_module: str = "xtquant",
        subscribe_live_quotes: bool = True,
    ) -> None:
        self.symbols = symbols
        self.period = period
        self.bar_window = bar_window
        self.subscribe_live_quotes = subscribe_live_quotes
        try:
            self.xtdata = importlib.import_module(f"{xtquant_module}.xtdata")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"QMT live data provider requires module '{xtquant_module}.xtdata'."
            ) from exc

    def load(self) -> list[Bar]:
        if self.subscribe_live_quotes:
            self._subscribe_quotes()

        frame_map = self._fetch_market_data()
        bars: list[Bar] = []
        for symbol in self.symbols:
            symbol_frame = self._resolve_symbol_frame(frame_map, symbol)
            if symbol_frame is None or symbol_frame.empty:
                continue
            normalized = self._normalize_frame(symbol_frame, symbol)
            bars.extend(normalized)
        bars.sort(key=lambda item: (item.timestamp, item.symbol))
        return bars

    def _subscribe_quotes(self) -> None:
        subscribe_quote = getattr(self.xtdata, "subscribe_quote", None)
        if subscribe_quote is None:
            return
        for symbol in self.symbols:
            try:
                subscribe_quote(stock_code=symbol, period=self.period, count=self.bar_window)
            except TypeError:
                subscribe_quote(symbol, self.period, self.bar_window)

    def _fetch_market_data(self) -> Any:
        get_market_data_ex = getattr(self.xtdata, "get_market_data_ex", None)
        if get_market_data_ex is None:
            raise RuntimeError("xtdata.get_market_data_ex is not available in the installed QMT SDK")
        try:
            return get_market_data_ex(
                field_list=["time", "open", "high", "low", "close", "volume"],
                stock_list=self.symbols,
                period=self.period,
                count=self.bar_window,
            )
        except TypeError:
            return get_market_data_ex(
                ["time", "open", "high", "low", "close", "volume"],
                self.symbols,
                self.period,
                count=self.bar_window,
            )

    def _resolve_symbol_frame(self, payload: Any, symbol: str) -> pd.DataFrame | None:
        if isinstance(payload, dict):
            candidate = payload.get(symbol)
            if isinstance(candidate, pd.DataFrame):
                return candidate
            if isinstance(candidate, dict):
                return pd.DataFrame(candidate)
        if isinstance(payload, pd.DataFrame):
            return payload
        return None

    def _normalize_frame(self, frame: pd.DataFrame, symbol: str) -> list[Bar]:
        working = frame.copy()
        if "time" not in working.columns:
            index_name = str(working.index.name or "").lower()
            if index_name in {"time", "datetime"}:
                working = working.reset_index()
            elif len(working.index) and isinstance(working.index[0], (datetime, pd.Timestamp)):
                working = working.reset_index().rename(columns={working.columns[0]: "time"})

        rename_map = {
            "datetime": "time",
            "vol": "volume",
        }
        working = working.rename(columns=rename_map)
        required = {"time", "open", "high", "low", "close", "volume"}
        missing = required - set(working.columns)
        if missing:
            raise RuntimeError(f"QMT live data frame missing columns: {', '.join(sorted(missing))}")

        bars: list[Bar] = []
        for row in working.itertuples(index=False):
            timestamp = self._normalize_timestamp(getattr(row, "time"))
            bars.append(
                Bar(
                    symbol=symbol,
                    timestamp=timestamp,
                    open=float(getattr(row, "open")),
                    high=float(getattr(row, "high")),
                    low=float(getattr(row, "low")),
                    close=float(getattr(row, "close")),
                    volume=float(getattr(row, "volume")),
                )
            )
        return bars

    def _normalize_timestamp(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()
        text = str(value)
        if text.isdigit():
            if len(text) >= 13:
                return datetime.fromtimestamp(int(text[:13]) / 1000)
            if len(text) == 14:
                return datetime.strptime(text, "%Y%m%d%H%M%S")
            if len(text) == 8:
                return datetime.strptime(text, "%Y%m%d")
        return datetime.fromisoformat(text)
