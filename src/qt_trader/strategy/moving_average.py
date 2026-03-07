from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from qt_trader.models import Bar, OrderSide, Signal
from qt_trader.strategy.base import Strategy


@dataclass(slots=True)
class SymbolState:
    closes: deque[float]
    has_position: bool = False


class MovingAverageCrossStrategy(Strategy):
    def __init__(self, symbols: list[str], fast_window: int, slow_window: int, trade_size: int) -> None:
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window")

        self.symbols = set(symbols)
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.trade_size = trade_size
        self._states: dict[str, SymbolState] = {}

    def on_bar(self, bar: Bar) -> list[Signal]:
        if bar.symbol not in self.symbols:
            return []

        # Each symbol tracks its own rolling close window so the same strategy
        # instance can run across a multi-asset universe.
        state = self._states.setdefault(bar.symbol, SymbolState(closes=deque(maxlen=self.slow_window)))
        state.closes.append(bar.close)
        if len(state.closes) < self.slow_window:
            return []

        fast = sum(list(state.closes)[-self.fast_window :]) / self.fast_window
        slow = sum(state.closes) / self.slow_window

        # Buy when short-term trend overtakes long-term trend, and exit when the
        # relationship flips back below the slower average.
        if fast > slow and not state.has_position:
            state.has_position = True
            return [Signal(symbol=bar.symbol, side=OrderSide.BUY, quantity=self.trade_size, reason="fast_ma_breakout")]

        if fast < slow and state.has_position:
            state.has_position = False
            return [Signal(symbol=bar.symbol, side=OrderSide.SELL, quantity=self.trade_size, reason="fast_ma_breakdown")]

        return []
