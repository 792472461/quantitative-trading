from __future__ import annotations

from qt_trader.broker.base import BrokerGateway
from qt_trader.models import Fill, Order


class PaperBroker(BrokerGateway):
    def __init__(self, commission_rate: float) -> None:
        self.commission_rate = commission_rate

    def submit_order(self, order: Order, market_price: float) -> Fill:
        commission = market_price * order.quantity * self.commission_rate
        return Fill(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=market_price,
            timestamp=order.timestamp,
            commission=commission,
        )
