from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from qt_trader.models import Bar, OrderSide, Signal
from qt_trader.strategy.base import Strategy


@dataclass(slots=True)
class SymbolState:
    closes: deque[float]
    has_position: bool = False


@dataclass(slots=True)
class MarketRegimeState:
    closes: deque[float]
    is_bullish: bool = False


class MovingAverageCrossStrategy(Strategy):
    def __init__(
        self,
        symbols: list[str],
        fast_window: int,
        slow_window: int,
        trade_size: int,
        market_filter_enabled: bool = False,
        benchmark_symbol: str | None = None,
        market_fast_window: int | None = None,
        market_slow_window: int | None = None,
    ) -> None:
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window")
        resolved_market_fast = fast_window if market_fast_window is None else market_fast_window
        resolved_market_slow = slow_window if market_slow_window is None else market_slow_window
        if resolved_market_fast >= resolved_market_slow:
            raise ValueError("market_fast_window must be smaller than market_slow_window")
        if market_filter_enabled and not benchmark_symbol:
            raise ValueError("benchmark_symbol is required when market_filter_enabled is enabled")

        self.symbols = set(symbols)
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.trade_size = trade_size
        self.market_filter_enabled = market_filter_enabled
        self.benchmark_symbol = benchmark_symbol
        self.market_fast_window = resolved_market_fast
        self.market_slow_window = resolved_market_slow
        self._states: dict[str, SymbolState] = {}
        self._market_state: MarketRegimeState | None = None

    def on_bar(self, bar: Bar) -> list[Signal]:
        if self.market_filter_enabled and bar.symbol == self.benchmark_symbol:
            self._update_market_regime(bar.close)
            return []

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
        if fast > slow and not state.has_position and self._can_open_position():
            state.has_position = True
            reason = "fast_ma_breakout"
            if self.market_filter_enabled:
                reason = "fast_ma_breakout_market_confirmed"
            return [Signal(symbol=bar.symbol, side=OrderSide.BUY, quantity=self.trade_size, reason=reason)]

        if fast < slow and state.has_position:
            state.has_position = False
            return [Signal(symbol=bar.symbol, side=OrderSide.SELL, quantity=self.trade_size, reason="fast_ma_breakdown")]

        return []

    def _update_market_regime(self, close: float) -> None:
        state = self._market_state
        if state is None:
            state = MarketRegimeState(closes=deque(maxlen=self.market_slow_window))
            self._market_state = state
        state.closes.append(close)
        if len(state.closes) < self.market_slow_window:
            state.is_bullish = False
            return
        fast = sum(list(state.closes)[-self.market_fast_window :]) / self.market_fast_window
        slow = sum(state.closes) / self.market_slow_window
        state.is_bullish = fast > slow

    def _can_open_position(self) -> bool:
        if not self.market_filter_enabled:
            return True
        if self._market_state is None:
            return False
        return self._market_state.is_bullish
