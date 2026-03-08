from __future__ import annotations

from qt_trader.models import Order, OrderSide, PortfolioSnapshot, Position


class RiskManager:
    def __init__(
        self,
        max_position_pct: float,
        max_drawdown_pct: float,
        max_total_exposure_pct: float = 0.8,
        max_positions: int = 10,
        max_symbol_quantity: int = 10000,
        t_plus_one_sell: bool = True,
    ) -> None:
        self.max_position_pct = max_position_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_total_exposure_pct = max_total_exposure_pct
        self.max_positions = max_positions
        self.max_symbol_quantity = max_symbol_quantity
        self.t_plus_one_sell = t_plus_one_sell

    def validate_order(
        self,
        order: Order,
        portfolio: PortfolioSnapshot,
        current_price: float,
        existing_position: Position | None,
    ) -> tuple[bool, str]:
        if portfolio.drawdown >= self.max_drawdown_pct:
            return False, "max drawdown exceeded"

        if order.side == OrderSide.SELL:
            if existing_position is None or existing_position.quantity < order.quantity:
                return False, "insufficient position"
            if self.t_plus_one_sell:
                blocked_quantity = 0
                if existing_position.t1_blocked_date == order.timestamp.date():
                    blocked_quantity = existing_position.t1_blocked_quantity
                sellable_quantity = existing_position.quantity - blocked_quantity
                if order.quantity > sellable_quantity:
                    return False, "t+1 sell blocked"
            return True, ""

        order_value = current_price * order.quantity
        if order_value > portfolio.total_value * self.max_position_pct:
            return False, "position size limit exceeded"
        if order_value > portfolio.cash:
            return False, "insufficient cash"
        if self._post_trade_exposure(portfolio, order_value) > self.max_total_exposure_pct:
            return False, "total exposure limit exceeded"
        if self._post_trade_position_count(portfolio, order.symbol, existing_position) > self.max_positions:
            return False, "max positions exceeded"
        current_quantity = 0 if existing_position is None else existing_position.quantity
        if current_quantity + order.quantity > self.max_symbol_quantity:
            return False, "symbol quantity limit exceeded"

        return True, ""

    def _post_trade_exposure(self, portfolio: PortfolioSnapshot, order_value: float) -> float:
        post_trade_positions_value = portfolio.positions_value + order_value
        if portfolio.total_value <= 0:
            return 1.0
        return post_trade_positions_value / portfolio.total_value

    def _post_trade_position_count(
        self,
        portfolio: PortfolioSnapshot,
        symbol: str,
        existing_position: Position | None,
    ) -> int:
        active_positions = sum(1 for position in portfolio.positions.values() if position.quantity > 0)
        if existing_position is None or existing_position.quantity == 0:
            active_positions += 1
        return active_positions
