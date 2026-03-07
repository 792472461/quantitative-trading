from __future__ import annotations

from qt_trader.broker.base import BrokerGateway
from qt_trader.costs import ExecutionCostModel
from qt_trader.models import Fill, Order


class PaperBroker(BrokerGateway):
    def __init__(self, cost_model: ExecutionCostModel) -> None:
        self.cost_model = cost_model

    def submit_order(self, order: Order, market_price: float) -> Fill:
        execution_price = self.cost_model.execution_price(market_price, order.side)
        commission = self.cost_model.commission(execution_price, order.quantity)
        stamp_duty = self.cost_model.stamp_duty(execution_price, order.quantity, order.side)
        slippage_cost = self.cost_model.slippage_cost(market_price, execution_price, order.quantity, order.side)
        return Fill(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=execution_price,
            timestamp=order.timestamp,
            commission=commission,
            stamp_duty=stamp_duty,
            slippage_cost=slippage_cost,
        )
