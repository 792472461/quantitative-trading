from __future__ import annotations

from dataclasses import dataclass

from qt_trader.models import OrderSide


@dataclass(slots=True)
class ExecutionCostModel:
    commission_rate: float
    min_commission: float
    stamp_duty_rate: float
    slippage_bps: float

    def execution_price(self, market_price: float, side: OrderSide) -> float:
        slippage_multiplier = self.slippage_bps / 10000
        if side == OrderSide.BUY:
            return market_price * (1 + slippage_multiplier)
        return market_price * (1 - slippage_multiplier)

    def commission(self, execution_price: float, quantity: int) -> float:
        gross = execution_price * quantity
        return max(gross * self.commission_rate, self.min_commission)

    def stamp_duty(self, execution_price: float, quantity: int, side: OrderSide) -> float:
        if side != OrderSide.SELL:
            return 0.0
        return execution_price * quantity * self.stamp_duty_rate

    def slippage_cost(self, market_price: float, execution_price: float, quantity: int, side: OrderSide) -> float:
        if side == OrderSide.BUY:
            return max(execution_price - market_price, 0.0) * quantity
        return max(market_price - execution_price, 0.0) * quantity
