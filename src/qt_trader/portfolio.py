from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from qt_trader.models import Fill, OrderSide, PortfolioSnapshot, Position


class Portfolio:
    def __init__(self, initial_cash: float) -> None:
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: dict[str, Position] = {}
        self.high_watermark = initial_cash

    def apply_fill(self, fill: Fill) -> None:
        position = self.positions.setdefault(fill.symbol, Position(symbol=fill.symbol))
        gross = fill.price * fill.quantity
        total_fees = fill.total_fees
        cost = gross + total_fees
        fill_date = fill.timestamp.date()

        if fill.side == OrderSide.BUY:
            total_cost = position.average_cost * position.quantity + cost
            position.quantity += fill.quantity
            position.average_cost = total_cost / position.quantity
            position.last_buy_timestamp = fill.timestamp
            if position.t1_blocked_date == fill_date:
                position.t1_blocked_quantity += fill.quantity
            else:
                position.t1_blocked_date = fill_date
                position.t1_blocked_quantity = fill.quantity
            self.cash -= cost
        else:
            position.quantity -= fill.quantity
            self.cash += gross - total_fees
            if position.quantity == 0:
                position.average_cost = 0.0
                position.last_buy_timestamp = None
                position.t1_blocked_date = None
                position.t1_blocked_quantity = 0

    def snapshot(self, timestamp: datetime, latest_prices: dict[str, float]) -> PortfolioSnapshot:
        positions_value = 0.0
        cloned_positions = deepcopy(self.positions)
        for symbol, position in cloned_positions.items():
            price = latest_prices.get(symbol, position.average_cost)
            positions_value += price * position.quantity

        total_value = self.cash + positions_value
        self.high_watermark = max(self.high_watermark, total_value)
        drawdown = 0.0 if self.high_watermark == 0 else 1 - total_value / self.high_watermark

        return PortfolioSnapshot(
            timestamp=timestamp,
            cash=self.cash,
            total_value=total_value,
            positions_value=positions_value,
            drawdown=drawdown,
            positions=cloned_positions,
        )
