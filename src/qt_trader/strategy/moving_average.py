from __future__ import annotations

from collections import deque

from qt_trader.models import Bar, OrderSide, Signal
from qt_trader.strategy.base import Strategy


class MovingAverageCrossStrategy(Strategy):
    def __init__(self, symbol: str, fast_window: int, slow_window: int, trade_size: int) -> None:
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window")

        self.symbol = symbol
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.trade_size = trade_size
        self._closes: deque[float] = deque(maxlen=slow_window)
        self._has_position = False

    def on_bar(self, bar: Bar) -> list[Signal]:
        if bar.symbol != self.symbol:
            return []

        self._closes.append(bar.close)
        if len(self._closes) < self.slow_window:
            return []

        fast = sum(list(self._closes)[-self.fast_window :]) / self.fast_window
        slow = sum(self._closes) / self.slow_window

        if fast > slow and not self._has_position:
            self._has_position = True
            return [Signal(symbol=bar.symbol, side=OrderSide.BUY, quantity=self.trade_size, reason="fast_ma_breakout")]

        if fast < slow and self._has_position:
            self._has_position = False
            return [Signal(symbol=bar.symbol, side=OrderSide.SELL, quantity=self.trade_size, reason="fast_ma_breakdown")]

        return []
