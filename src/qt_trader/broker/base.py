from __future__ import annotations

from abc import ABC, abstractmethod

from qt_trader.models import AccountInfo, Fill, Order, OrderInfo, PositionInfo, TradeInfo


class BrokerGateway(ABC):
    @abstractmethod
    def submit_order(self, order: Order, market_price: float) -> Fill:
        raise NotImplementedError

    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> list[PositionInfo]:
        raise NotImplementedError

    @abstractmethod
    def get_orders(self) -> list[OrderInfo]:
        raise NotImplementedError

    @abstractmethod
    def get_trades(self) -> list[TradeInfo]:
        raise NotImplementedError
