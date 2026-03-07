from __future__ import annotations

from dataclasses import dataclass, field

from qt_trader.broker.base import BrokerGateway
from qt_trader.models import Bar, Fill, Order, OrderStatus, PortfolioSnapshot
from qt_trader.portfolio import Portfolio
from qt_trader.risk import RiskManager
from qt_trader.strategy.base import Strategy


@dataclass(slots=True)
class BacktestResult:
    snapshots: list[PortfolioSnapshot] = field(default_factory=list)
    rejected_orders: list[Order] = field(default_factory=list)
    executed_orders: list[Order] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)

    @property
    def final_snapshot(self) -> PortfolioSnapshot | None:
        return self.snapshots[-1] if self.snapshots else None


class BacktestEngine:
    def __init__(
        self,
        strategy: Strategy,
        broker: BrokerGateway,
        portfolio: Portfolio,
        risk_manager: RiskManager,
    ) -> None:
        self.strategy = strategy
        self.broker = broker
        self.portfolio = portfolio
        self.risk_manager = risk_manager

    def run(self, bars: list[Bar]) -> BacktestResult:
        result = BacktestResult()
        latest_prices: dict[str, float] = {}

        for bar in bars:
            latest_prices[bar.symbol] = bar.close
            signals = self.strategy.on_bar(bar)
            snapshot = self.portfolio.snapshot(bar.timestamp, latest_prices)

            for signal in signals:
                # Strategy only emits intent; order creation and risk checks happen here.
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
                    continue

                fill = self.broker.submit_order(order, bar.close)
                self.portfolio.apply_fill(fill)
                order.status = OrderStatus.FILLED
                result.executed_orders.append(order)
                result.fills.append(fill)

            result.snapshots.append(self.portfolio.snapshot(bar.timestamp, latest_prices))

        return result
