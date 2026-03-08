from __future__ import annotations

from pathlib import Path

from qt_trader.broker.base import BrokerGateway
from qt_trader.broker.qmt_sdk import QMTSdkClient
from qt_trader.models import AccountInfo, Fill, Order, OrderInfo, PositionInfo, TradeInfo


class GuojinQMTLiveBroker(BrokerGateway):
    def __init__(
        self,
        account_id: str,
        terminal_path: str | Path,
        client: QMTSdkClient,
        default_price_type: str = "latest",
        allow_live_trading: bool = False,
    ) -> None:
        self.account_id = account_id
        self.terminal_path = Path(terminal_path)
        self.client = client
        self.default_price_type = default_price_type
        self.allow_live_trading = allow_live_trading

    def submit_order(self, order: Order, market_price: float) -> Fill:
        raise RuntimeError(
            "Live QMT broker does not support synthetic immediate fills. "
            "Use the live trading runtime instead of paper trading."
        )

    def place_order(self, order: Order, market_price: float) -> OrderInfo:
        if not self.allow_live_trading:
            raise RuntimeError(
                "Live trading is disabled. Set broker.allow_live_trading=true after validating the QMT environment."
            )
        if self.default_price_type == "limit" and order.price is None:
            order.price = market_price
        return self.client.place_order(order, price_type=self.default_price_type)

    def get_account_info(self) -> AccountInfo:
        return self.client.get_account_info()

    def get_positions(self) -> list[PositionInfo]:
        return self.client.get_positions()

    def get_orders(self) -> list[OrderInfo]:
        return self.client.get_orders()

    def get_trades(self) -> list[TradeInfo]:
        return self.client.get_trades()
