from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date

from qt_trader.models import Bar, OrderSide, Signal
from qt_trader.strategy.base import Strategy


@dataclass(slots=True)
class SymbolSelectionState:
    closes: deque[float]
    volumes: deque[float]
    has_position: bool = False
    last_buy_date: date | None = None


@dataclass(slots=True)
class RankedCandidate:
    symbol: str
    score: float
    momentum: float
    volume_ratio: float
    rank: int


class AutoRotationStrategy(Strategy):
    def __init__(
        self,
        symbols: list[str],
        trade_size: int,
        selection_window: int = 5,
        selection_top_n: int = 3,
        selection_volume_window: int = 5,
        selection_exit_rank_buffer: int = 1,
        min_holding_days: int = 1,
    ) -> None:
        if selection_top_n > len(symbols):
            raise ValueError("selection_top_n cannot exceed symbol universe size")
        self.symbols = tuple(dict.fromkeys(symbols))
        self.trade_size = trade_size
        self.selection_window = selection_window
        self.selection_top_n = selection_top_n
        self.selection_volume_window = selection_volume_window
        self.selection_exit_rank_buffer = selection_exit_rank_buffer
        self.min_holding_days = min_holding_days
        window_size = max(selection_window + 1, selection_volume_window)
        self._states = {
            symbol: SymbolSelectionState(
                closes=deque(maxlen=window_size),
                volumes=deque(maxlen=selection_volume_window),
            )
            for symbol in self.symbols
        }
        self._current_trading_date: date | None = None
        self._seen_symbols: set[str] = set()
        self._latest_closes: dict[str, float] = {}
        self._last_rebalanced_date: date | None = None

    def on_bar(self, bar: Bar) -> list[Signal]:
        if bar.symbol not in self._states:
            return []

        trading_date = bar.timestamp.date()
        if self._current_trading_date != trading_date:
            self._current_trading_date = trading_date
            self._seen_symbols.clear()
            self._latest_closes.clear()
        if self._last_rebalanced_date == trading_date:
            state = self._states[bar.symbol]
            state.closes.append(bar.close)
            state.volumes.append(bar.volume)
            self._latest_closes[bar.symbol] = bar.close
            return []

        state = self._states[bar.symbol]
        state.closes.append(bar.close)
        state.volumes.append(bar.volume)
        self._seen_symbols.add(bar.symbol)
        self._latest_closes[bar.symbol] = bar.close

        if self._seen_symbols != set(self.symbols):
            return []

        rankings = self._rank_candidates()
        if not rankings:
            return []

        hold_cutoff_rank = self.selection_top_n + self.selection_exit_rank_buffer
        rank_map = {candidate.symbol: candidate for candidate in rankings}
        signals: list[Signal] = []

        for symbol, item_state in self._states.items():
            candidate = rank_map.get(symbol)
            if item_state.has_position:
                should_hold = (
                    candidate is not None
                    and candidate.score > 0
                    and candidate.rank <= hold_cutoff_rank
                )
                if should_hold:
                    continue
                if not self._can_sell(item_state, trading_date):
                    continue
                item_state.has_position = False
                signals.append(
                    Signal(
                        symbol=symbol,
                        side=OrderSide.SELL,
                        quantity=self.trade_size,
                        reason="auto_rotation_exit",
                        reference_price=self._latest_closes.get(symbol),
                    )
                )

        for symbol in [candidate.symbol for candidate in rankings[: self.selection_top_n] if candidate.score > 0]:
            item_state = self._states[symbol]
            if item_state.has_position:
                continue
            item_state.has_position = True
            item_state.last_buy_date = trading_date
            signals.append(
                Signal(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    quantity=self.trade_size,
                    reason="auto_rotation_entry",
                    reference_price=self._latest_closes.get(symbol),
                )
            )

        self._last_rebalanced_date = trading_date
        return signals

    def _rank_candidates(self) -> list[RankedCandidate]:
        candidates: list[RankedCandidate] = []
        for symbol, state in self._states.items():
            if len(state.closes) < self.selection_window + 1 or len(state.volumes) < self.selection_volume_window:
                continue
            closes = list(state.closes)
            current_close = closes[-1]
            anchor_close = closes[-self.selection_window - 1]
            if anchor_close <= 0:
                continue
            momentum = current_close / anchor_close - 1
            average_volume = sum(state.volumes) / len(state.volumes)
            volume_ratio = 0.0 if average_volume <= 0 else state.volumes[-1] / average_volume
            score = momentum + max(volume_ratio - 1.0, 0.0) * 0.1
            candidates.append(
                RankedCandidate(
                    symbol=symbol,
                    score=score,
                    momentum=momentum,
                    volume_ratio=volume_ratio,
                    rank=0,
                )
            )

        candidates.sort(key=lambda item: (item.score, item.momentum, item.volume_ratio), reverse=True)
        for index, candidate in enumerate(candidates, start=1):
            candidate.rank = index
        return candidates

    def _can_sell(self, state: SymbolSelectionState, trading_date: date) -> bool:
        if state.last_buy_date is None:
            return True
        return (trading_date - state.last_buy_date).days >= self.min_holding_days
