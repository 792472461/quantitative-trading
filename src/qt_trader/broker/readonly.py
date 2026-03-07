from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from qt_trader.broker.base import BrokerGateway
from qt_trader.models import AccountInfo, Fill, Order, OrderInfo, PositionInfo


class ReadOnlyBroker(BrokerGateway):
    def __init__(self, broker_name: str, account_id: str, state_file: str | Path, environment: str = "readonly") -> None:
        self.broker_name = broker_name
        self.account_id = account_id
        self.state_file = Path(state_file)
        self.environment = environment

    def submit_order(self, order: Order, market_price: float) -> Fill:
        raise RuntimeError(
            f"Broker '{self.broker_name}' is configured as read-only. Real order submission is disabled."
        )

    def get_account_info(self) -> AccountInfo:
        payload = self._load_state()
        account = payload.get("account", {})
        return AccountInfo(
            account_id=str(account.get("account_id", self.account_id)),
            broker=self.broker_name,
            cash=float(account.get("cash", 0.0)),
            total_equity=float(account.get("total_equity", 0.0)),
            buying_power=float(account.get("buying_power", 0.0)),
            environment=str(account.get("environment", self.environment)),
        )

    def get_positions(self) -> list[PositionInfo]:
        payload = self._load_state()
        positions = []
        for item in payload.get("positions", []):
            positions.append(
                PositionInfo(
                    symbol=str(item["symbol"]),
                    quantity=int(item["quantity"]),
                    average_cost=float(item["average_cost"]),
                    market_price=float(item["market_price"]),
                    market_value=float(item["market_value"]),
                )
            )
        return positions

    def get_orders(self) -> list[OrderInfo]:
        payload = self._load_state()
        orders = []
        for item in payload.get("orders", []):
            orders.append(
                OrderInfo(
                    symbol=str(item["symbol"]),
                    side=str(item["side"]),
                    quantity=int(item["quantity"]),
                    price=None if item.get("price") is None else float(item["price"]),
                    status=str(item["status"]),
                    timestamp=datetime.fromisoformat(str(item["timestamp"])),
                    reason=str(item.get("reason", "")),
                )
            )
        return orders

    def _load_state(self) -> dict:
        if not self.state_file.exists():
            return {"account": {}, "positions": [], "orders": []}
        return json.loads(self.state_file.read_text(encoding="utf-8"))
