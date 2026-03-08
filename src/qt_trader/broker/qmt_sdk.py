from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from qt_trader.broker.terminal_client import TerminalClient
from qt_trader.models import AccountInfo, Order, OrderInfo, OrderSide, PositionInfo, TradeInfo


class QMTQueryAdapter(Protocol):
    def get_account_info(self) -> AccountInfo:
        ...

    def get_positions(self) -> list[PositionInfo]:
        ...

    def get_orders(self) -> list[OrderInfo]:
        ...

    def place_order(self, order: Order, price_type: str = "latest") -> OrderInfo:
        ...

    def get_trades(self) -> list[TradeInfo]:
        ...


@dataclass(slots=True)
class QMTSdkBundle:
    XtQuantTrader: type
    StockAccount: type
    xtconstant: Any | None = None


@dataclass(slots=True)
class QMTSdkClient(TerminalClient):
    broker_name: str
    account_id: str
    terminal_path: str
    environment: str = "qmt_sdk_readonly"
    sdk_module: str = "xtquant"
    session_id: int = 1
    terminal_userdata_path: str | None = None
    adapter: QMTQueryAdapter | None = None
    sdk_bundle: QMTSdkBundle | None = None

    def __post_init__(self) -> None:
        if self.adapter is None:
            self.adapter = self._build_adapter()

    def get_account_info(self) -> AccountInfo:
        return self.adapter.get_account_info()

    def get_positions(self) -> list[PositionInfo]:
        return self.adapter.get_positions()

    def get_orders(self) -> list[OrderInfo]:
        return self.adapter.get_orders()

    def place_order(self, order: Order, price_type: str = "latest") -> OrderInfo:
        return self.adapter.place_order(order, price_type=price_type)

    def get_trades(self) -> list[TradeInfo]:
        return self.adapter.get_trades()

    def _build_adapter(self) -> QMTQueryAdapter:
        bundle = self.sdk_bundle or self._load_sdk_bundle()
        userdata_path = self._resolve_userdata_path()
        return XtQuantTraderQueryAdapter(
            broker_name=self.broker_name,
            account_id=self.account_id,
            environment=self.environment,
            userdata_path=userdata_path,
            session_id=self.session_id,
            sdk_bundle=bundle,
        )

    def _load_sdk_bundle(self) -> QMTSdkBundle:
        try:
            xttrader_module = importlib.import_module(f"{self.sdk_module}.xttrader")
            xttype_module = importlib.import_module(f"{self.sdk_module}.xttype")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"QMT SDK module '{self.sdk_module}' is not installed. "
                "Install the broker SDK or switch broker.terminal_client_mode back to 'mock'."
            ) from exc
        try:
            xtconstant_module = importlib.import_module(f"{self.sdk_module}.xtconstant")
        except ModuleNotFoundError:
            xtconstant_module = None

        if not hasattr(xttrader_module, "XtQuantTrader") or not hasattr(xttype_module, "StockAccount"):
            raise RuntimeError(
                f"QMT SDK module '{self.sdk_module}' is missing XtQuantTrader or StockAccount."
            )

        return QMTSdkBundle(
            XtQuantTrader=xttrader_module.XtQuantTrader,
            StockAccount=xttype_module.StockAccount,
            xtconstant=xtconstant_module,
        )

    def _resolve_userdata_path(self) -> Path:
        if self.terminal_userdata_path is not None:
            return Path(self.terminal_userdata_path)

        terminal_path = Path(self.terminal_path)
        candidates = (
            terminal_path / "userdata_mini",
            terminal_path / "userdata",
            terminal_path,
        )
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]


@dataclass(slots=True)
class XtQuantTraderQueryAdapter(QMTQueryAdapter):
    broker_name: str
    account_id: str
    environment: str
    userdata_path: Path
    session_id: int
    sdk_bundle: QMTSdkBundle

    def __post_init__(self) -> None:
        self.account = self.sdk_bundle.StockAccount(self.account_id)
        self.trader = self.sdk_bundle.XtQuantTrader(str(self.userdata_path), self.session_id)
        self.xtconstant = self.sdk_bundle.xtconstant
        self.trader.start()
        connect_result = self.trader.connect()
        if connect_result != 0:
            raise RuntimeError(f"QMT connect failed with code={connect_result}")
        subscribe_result = self.trader.subscribe(self.account)
        if subscribe_result != 0:
            raise RuntimeError(f"QMT subscribe failed with code={subscribe_result}")

    def get_account_info(self) -> AccountInfo:
        asset = self.trader.query_stock_asset(self.account)
        cash = _float_attr(asset, "enable_balance", "cash", default=0.0)
        total_equity = _float_attr(asset, "total_asset", "total_equity", default=cash)
        buying_power = _float_attr(asset, "buying_power", "enable_balance", "cash", default=cash)
        return AccountInfo(
            account_id=self.account_id,
            broker=self.broker_name,
            cash=cash,
            total_equity=total_equity,
            buying_power=buying_power,
            environment=self.environment,
        )

    def get_positions(self) -> list[PositionInfo]:
        items = self.trader.query_stock_positions(self.account) or []
        positions: list[PositionInfo] = []
        for item in items:
            quantity = _int_attr(item, "volume", "quantity", default=0)
            market_price = _float_attr(item, "last_price", "market_price", "price", default=0.0)
            average_cost = _float_attr(item, "open_price", "avg_price", "average_cost", default=0.0)
            market_value = _float_attr(item, "market_value", "stock_value", default=quantity * market_price)
            positions.append(
                PositionInfo(
                    symbol=_str_attr(item, "stock_code", "symbol", "code", default=""),
                    quantity=quantity,
                    average_cost=average_cost,
                    market_price=market_price,
                    market_value=market_value,
                )
            )
        return positions

    def get_orders(self) -> list[OrderInfo]:
        items = self.trader.query_stock_orders(self.account) or []
        orders: list[OrderInfo] = []
        for item in items:
            orders.append(
                OrderInfo(
                    symbol=_str_attr(item, "stock_code", "symbol", "code", default=""),
                    side=_normalize_order_side(_raw_attr(item, "order_type", "side", "direction")),
                    quantity=_int_attr(item, "order_volume", "volume", "quantity", default=0),
                    price=_optional_float_attr(item, "price", "price_value", "order_price"),
                    status=_normalize_order_status(_raw_attr(item, "order_status", "status", "status_msg")),
                    timestamp=_normalize_timestamp(_raw_attr(item, "order_time", "timestamp", "traded_time")),
                    broker_order_id=_str_attr(item, "order_id", "entrust_no", "order_sysid", default=""),
                    reason=_str_attr(item, "order_remark", "remark", "reason", default=""),
                )
            )
        return orders

    def get_trades(self) -> list[TradeInfo]:
        if not hasattr(self.trader, "query_stock_trades"):
            return []
        items = self.trader.query_stock_trades(self.account) or []
        trades: list[TradeInfo] = []
        for item in items:
            trades.append(
                TradeInfo(
                    symbol=_str_attr(item, "stock_code", "symbol", "code", default=""),
                    side=_normalize_order_side(_raw_attr(item, "order_type", "side", "direction")),
                    quantity=_int_attr(item, "traded_volume", "volume", "quantity", default=0),
                    price=_float_attr(item, "traded_price", "price", "deal_price", default=0.0),
                    timestamp=_normalize_timestamp(_raw_attr(item, "traded_time", "timestamp", "trade_time")),
                    broker_order_id=_str_attr(item, "order_id", "entrust_no", "order_sysid", default=""),
                    trade_id=_str_attr(item, "trade_id", "deal_id", "business_id", default=""),
                    reason=_str_attr(item, "remark", "reason", default=""),
                )
            )
        return trades

    def place_order(self, order: Order, price_type: str = "latest") -> OrderInfo:
        order_type = self._resolve_order_type(order.side)
        resolved_price_type = self._resolve_price_type(price_type)
        submit_price = order.price if order.price is not None else 0.0

        if hasattr(self.trader, "order_stock_async"):
            order_id = self.trader.order_stock_async(
                self.account,
                order.symbol,
                order_type,
                int(order.quantity),
                resolved_price_type,
                float(submit_price),
                "qt_trader",
                order.reason or "qt_trader_live",
            )
        elif hasattr(self.trader, "order_stock"):
            order_id = self.trader.order_stock(
                self.account,
                order.symbol,
                order_type,
                int(order.quantity),
                resolved_price_type,
                float(submit_price),
                "qt_trader",
                order.reason or "qt_trader_live",
            )
        else:
            raise RuntimeError("QMT trader does not expose order_stock or order_stock_async")

        if order_id in {None, -1, 0}:
            raise RuntimeError(f"QMT order submission failed, order_id={order_id}")

        return OrderInfo(
            symbol=order.symbol,
            side=order.side.value,
            quantity=order.quantity,
            price=order.price,
            status="SUBMITTED",
            timestamp=order.timestamp,
            broker_order_id=str(order_id),
            reason=order.reason,
        )

    def _resolve_order_type(self, side: OrderSide) -> int:
        if self.xtconstant is None:
            raise RuntimeError("QMT xtconstant module is required for live order submission")
        if side == OrderSide.BUY:
            return int(getattr(self.xtconstant, "STOCK_BUY"))
        return int(getattr(self.xtconstant, "STOCK_SELL"))

    def _resolve_price_type(self, price_type: str) -> int:
        if self.xtconstant is None:
            raise RuntimeError("QMT xtconstant module is required for live order submission")
        normalized = price_type.strip().lower()
        if normalized == "latest":
            candidate = getattr(self.xtconstant, "LATEST_PRICE", None)
            if candidate is None:
                candidate = getattr(self.xtconstant, "MARKET_PEER_PRICE_FIRST", None)
            if candidate is None:
                raise RuntimeError("QMT xtconstant does not expose a latest/market price type")
            return int(candidate)
        if normalized == "limit":
            candidate = getattr(self.xtconstant, "FIX_PRICE", None)
            if candidate is None:
                raise RuntimeError("QMT xtconstant does not expose FIX_PRICE")
            return int(candidate)
        raise RuntimeError(f"Unsupported QMT live order price type: {price_type}")


def _raw_attr(obj: Any, *names: str) -> Any:
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _str_attr(obj: Any, *names: str, default: str = "") -> str:
    value = _raw_attr(obj, *names)
    return default if value is None else str(value)


def _int_attr(obj: Any, *names: str, default: int = 0) -> int:
    value = _raw_attr(obj, *names)
    return default if value is None else int(value)


def _float_attr(obj: Any, *names: str, default: float = 0.0) -> float:
    value = _raw_attr(obj, *names)
    return default if value is None else float(value)


def _optional_float_attr(obj: Any, *names: str) -> float | None:
    value = _raw_attr(obj, *names)
    return None if value is None else float(value)


def _normalize_order_side(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).upper()
    if text in {"23", "BUY", "B", "LONG"}:
        return "BUY"
    if text in {"24", "SELL", "S", "SHORT"}:
        return "SELL"
    return text


def _normalize_order_status(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).upper()
    if text in {"CANCELLED", "CANCELED", "CANCEL", "撤单", "已撤", "废单", "REJECTED", "INVALID"}:
        return "CANCELED"
    if text in {"PART_FILLED", "PARTIALLY_FILLED", "PARTIAL_FILLED", "部分成交", "部成"}:
        return "PARTIALLY_FILLED"
    if text in {"FILLED", "ALL_TRADED", "已成", "全部成交"}:
        return "FILLED"
    if text in {"NEW", "SUBMITTED", "已报", "未成", "PENDING"}:
        return "SUBMITTED"
    return text


def _normalize_timestamp(value: Any) -> datetime:
    if value is None:
        return datetime.fromisoformat("1970-01-01T00:00:00")
    text = str(value)
    if text.isdigit():
        if len(text) == 14:
            return datetime.strptime(text, "%Y%m%d%H%M%S")
        if len(text) == 8:
            return datetime.strptime(text, "%Y%m%d")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.fromisoformat("1970-01-01T00:00:00")
