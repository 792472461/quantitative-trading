from __future__ import annotations

from qt_trader.models import Order, OrderSide, PortfolioSnapshot, Position


class RiskManager:
    def __init__(self, max_position_pct: float, max_drawdown_pct: float) -> None:
        self.max_position_pct = max_position_pct
        self.max_drawdown_pct = max_drawdown_pct

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
            return True, ""

        order_value = current_price * order.quantity
        if order_value > portfolio.total_value * self.max_position_pct:
            return False, "position size limit exceeded"
        if order_value > portfolio.cash:
            return False, "insufficient cash"

        return True, ""
