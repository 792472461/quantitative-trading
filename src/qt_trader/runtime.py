from __future__ import annotations

import time
from dataclasses import dataclass, field

from qt_trader.broker.base import BrokerGateway
from qt_trader.models import Bar, Order, OrderStatus, PortfolioSnapshot
from qt_trader.portfolio import Portfolio
from qt_trader.risk import RiskManager
from qt_trader.storage import SQLiteStorage
from qt_trader.strategy.base import Strategy


@dataclass(slots=True)
class RuntimeResult:
    snapshots: list[PortfolioSnapshot] = field(default_factory=list)
    executed_orders: list[Order] = field(default_factory=list)
    rejected_orders: list[Order] = field(default_factory=list)


class PaperTradingRuntime:
    def __init__(
        self,
        strategy: Strategy,
        broker: BrokerGateway,
        portfolio: Portfolio,
        risk_manager: RiskManager,
        storage: SQLiteStorage | None = None,
        persist_snapshots: bool = True,
        sleep_seconds: float = 0.0,
    ) -> None:
        self.strategy = strategy
        self.broker = broker
        self.portfolio = portfolio
        self.risk_manager = risk_manager
        self.storage = storage
        self.persist_snapshots = persist_snapshots
        self.sleep_seconds = sleep_seconds

    def run(self, bars: list[Bar]) -> RuntimeResult:
        result = RuntimeResult()
        latest_prices: dict[str, float] = {}

        for bar in bars:
            latest_prices[bar.symbol] = bar.close
            snapshot = self.portfolio.snapshot(bar.timestamp, latest_prices)

            for signal in self.strategy.on_bar(bar):
                order = Order(
                    symbol=signal.symbol,
                    side=signal.side,
                    quantity=signal.quantity,
                    timestamp=bar.timestamp,
                    price=bar.close,
                    reason=signal.reason,
                )
                existing_position = snapshot.positions.get(signal.symbol)
                accepted, reason = self.risk_manager.validate_order(order, snapshot, bar.close, existing_position)
                if not accepted:
                    order.status = OrderStatus.REJECTED
                    order.reason = reason
                    result.rejected_orders.append(order)
                    if self.storage is not None:
                        self.storage.save_order(order)
                    continue

                fill = self.broker.submit_order(order, bar.close)
                self.portfolio.apply_fill(fill)
                order.status = OrderStatus.FILLED
                result.executed_orders.append(order)

                if self.storage is not None:
                    self.storage.save_order(order)
                    self.storage.save_fill(fill)

            runtime_snapshot = self.portfolio.snapshot(bar.timestamp, latest_prices)
            result.snapshots.append(runtime_snapshot)
            if self.storage is not None and self.persist_snapshots:
                self.storage.save_snapshot(runtime_snapshot)

            if self.sleep_seconds > 0:
                time.sleep(self.sleep_seconds)

        return result
