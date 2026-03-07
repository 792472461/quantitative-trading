from __future__ import annotations

from abc import ABC, abstractmethod

from qt_trader.models import Fill, Order


class BrokerGateway(ABC):
    @abstractmethod
    def submit_order(self, order: Order, market_price: float) -> Fill:
        raise NotImplementedError
