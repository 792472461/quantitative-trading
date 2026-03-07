from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from qt_trader.broker.base import BrokerGateway
from qt_trader.models import AccountInfo, Fill, Order, OrderInfo, PositionInfo


class HTTPSessionProtocol(Protocol):
    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> Any:
        ...


class HTTPReadOnlyBroker(BrokerGateway):
    def __init__(
        self,
        broker_name: str,
        account_id: str,
        base_url: str,
        account_endpoint: str,
        positions_endpoint: str,
        orders_endpoint: str,
        api_key: str,
        api_secret: str,
        timeout_seconds: float = 10.0,
        session: HTTPSessionProtocol | None = None,
    ) -> None:
        self.broker_name = broker_name
        self.account_id = account_id
        self.base_url = base_url.rstrip("/")
        self.account_endpoint = account_endpoint
        self.positions_endpoint = positions_endpoint
        self.orders_endpoint = orders_endpoint
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout_seconds = timeout_seconds
        if session is None:
            import requests

            self.session = requests.Session()
        else:
            self.session = session

    def submit_order(self, order: Order, market_price: float) -> Fill:
        raise RuntimeError(
            f"Broker '{self.broker_name}' is configured as HTTP read-only. Real order submission is disabled."
        )

    def get_account_info(self) -> AccountInfo:
        payload = self._get_json(self.account_endpoint)
        account = payload.get("account", payload)
        return AccountInfo(
            account_id=str(account.get("account_id", self.account_id)),
            broker=self.broker_name,
            cash=float(account.get("cash", 0.0)),
            total_equity=float(account.get("total_equity", 0.0)),
            buying_power=float(account.get("buying_power", 0.0)),
            environment=str(account.get("environment", "readonly")),
        )

    def get_positions(self) -> list[PositionInfo]:
        payload = self._get_json(self.positions_endpoint)
        items = payload.get("positions", payload if isinstance(payload, list) else [])
        return [
            PositionInfo(
                symbol=str(item["symbol"]),
                quantity=int(item["quantity"]),
                average_cost=float(item["average_cost"]),
                market_price=float(item["market_price"]),
                market_value=float(item["market_value"]),
            )
            for item in items
        ]

    def get_orders(self) -> list[OrderInfo]:
        payload = self._get_json(self.orders_endpoint)
        items = payload.get("orders", payload if isinstance(payload, list) else [])
        return [
            OrderInfo(
                symbol=str(item["symbol"]),
                side=str(item["side"]),
                quantity=int(item["quantity"]),
                price=None if item.get("price") is None else float(item["price"]),
                status=str(item["status"]),
                timestamp=datetime.fromisoformat(str(item["timestamp"])),
                reason=str(item.get("reason", "")),
            )
            for item in items
        ]

    def _get_json(self, endpoint: str) -> dict[str, Any] | list[dict[str, Any]]:
        response = self.session.get(
            f"{self.base_url}{endpoint}",
            headers={
                "X-API-KEY": self.api_key,
                "X-API-SECRET": self.api_secret,
                "X-ACCOUNT-ID": self.account_id,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
