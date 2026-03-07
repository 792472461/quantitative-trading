from __future__ import annotations

from qt_trader.broker.base import BrokerGateway
from qt_trader.costs import ExecutionCostModel
from qt_trader.models import AccountInfo, Fill, Order, OrderInfo, PositionInfo
from qt_trader.portfolio import Portfolio


class PaperBroker(BrokerGateway):
    def __init__(self, cost_model: ExecutionCostModel, portfolio: Portfolio | None = None) -> None:
        self.cost_model = cost_model
        self.portfolio = portfolio
        self._orders: list[OrderInfo] = []

    def submit_order(self, order: Order, market_price: float) -> Fill:
        execution_price = self.cost_model.execution_price(market_price, order.side)
        commission = self.cost_model.commission(execution_price, order.quantity)
        stamp_duty = self.cost_model.stamp_duty(execution_price, order.quantity, order.side)
        slippage_cost = self.cost_model.slippage_cost(market_price, execution_price, order.quantity, order.side)
        self._orders.append(
            OrderInfo(
                symbol=order.symbol,
                side=order.side.value,
                quantity=order.quantity,
                price=execution_price,
                status="FILLED",
                timestamp=order.timestamp,
                reason=order.reason,
            )
        )
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

    def get_account_info(self) -> AccountInfo:
        cash = self.portfolio.cash if self.portfolio is not None else 0.0
        positions_value = 0.0
        if self.portfolio is not None:
            positions_value = sum(position.quantity * position.average_cost for position in self.portfolio.positions.values())
        total_equity = cash + positions_value
        return AccountInfo(
            account_id="paper-account",
            broker="paper",
            cash=cash,
            total_equity=total_equity,
            buying_power=cash,
            environment="paper",
        )

    def get_positions(self) -> list[PositionInfo]:
        if self.portfolio is None:
            return []
        positions: list[PositionInfo] = []
        for position in self.portfolio.positions.values():
            if position.quantity <= 0:
                continue
            market_value = position.quantity * position.average_cost
            positions.append(
                PositionInfo(
                    symbol=position.symbol,
                    quantity=position.quantity,
                    average_cost=position.average_cost,
                    market_price=position.average_cost,
                    market_value=market_value,
                )
            )
        return positions

    def get_orders(self) -> list[OrderInfo]:
        return list(self._orders)
